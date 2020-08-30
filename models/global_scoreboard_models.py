from __future__ import annotations
from datetime import datetime, timedelta
from math import ceil, exp, floor, pi
from models.game_search_models import GameValues
from services.utils import get_file, UserUpdaterError, start_and_wait_for_threads
from services.user_updater_helpers import BasicJSONType, extract_valid_personal_bests, get_probability_terms, \
    get_subcategory_variables, keep_runs_before_soft_cutoff, keep_last_full_game_runs, MIN_LEADERBOARD_SIZE
from threading import Thread
from typing import Dict, List, Optional, Tuple
from urllib import parse
import configs
import re
import traceback

TIME_BONUS_DIVISOR = 3600 * 12  # 12h (1/2 day) for +100%
MAX_RUNS_COUNT = 1000

memoized_requests: Dict[str, SrcRequest] = {}


class SrcRequest():
    global memoized_requests
    result: dict
    timestamp: datetime

    def __init__(self, result: dict, timestamp: datetime):
        self.result = result
        self.timestamp = timestamp

    @staticmethod
    def get_cached_response_or_new(url: str) -> dict:
        today = datetime.utcnow()
        yesterday = today - timedelta(days=configs.last_updated_days[0])

        try:
            cached_request = memoized_requests[url]
        except KeyError:
            cached_request = None
        if (cached_request and cached_request.timestamp >= yesterday):
            return cached_request.result
        else:
            result = get_file(url)
            memoized_requests[url] = SrcRequest(result, today)
            return result

    @staticmethod
    def get_paginated_response(url: str) -> dict:
        summed_results = {"data": []}
        next_url = url
        while next_url:
            max_param = parse.parse_qs(parse.urlparse(next_url).query).get('max')
            results_per_page = int(max_param[0]) if max_param else 20

            # Get the next page of results ...
            while True:
                try:
                    result = get_file(next_url)
                    break
                # If it failed, try again with a smaller page
                except UserUpdaterError as exception:
                    if exception.args[0]['error'] != "HTTPError 500" or results_per_page < 20:
                        raise exception
                    halved_results_per_page = floor(results_per_page / 2)
                    print("SRC returned 500 for a paginated request. "
                          f"Halving the max results per page from {results_per_page} to {halved_results_per_page}")
                    next_url = next_url.replace(f"max={results_per_page}", f"max={halved_results_per_page}")
                    results_per_page = halved_results_per_page

            # ... and combine it with previous ones
            next_url = next((link["uri"] for link in result["pagination"]["links"] if link["rel"] == "next"), None)
            summed_results["data"] += result["data"]

        return summed_results


class Run:
    id_: str = ""
    primary_t: float = 0.0
    game: str = ""
    game_name: str = ""
    category: str = ""
    category_name: str = ""
    variables = {}
    level: str = ""
    level_name: str = ""
    level_count: int = 0
    _points: float = 0
    # This below section is for game search
    _mean_time: float = 0
    _is_wr_time: bool = False
    _platform: Optional[str] = None

    # TODO: Reanable sonarlint max args rule
    def __init__(
            self,
            id_: str,
            primary_t: float,
            game: str,
            game_name: str,
            category: str,
            variables=None,
            level: str = "",
            level_name: str = "",
            level_count: int = 0):
        self.id_ = id_
        self.primary_t = primary_t
        self.game = game
        self.game_name = game_name
        self.category = category
        self.variables = variables if variables is not None else {}
        self.level = level
        self.level_name = level_name
        self.level_count = level_count
        self.__set_points()

    def __str__(self) -> str:
        level_str = f"Level/{self.level_count}: {self.level}, " if self.level else ""
        return f"Run: <Game: {self.game}, " \
               f"Category: {self.category}, {level_str}{self.variables} {ceil(self._points * 100) / 100}>"

    def __eq__(self, other) -> bool:
        """
        :type other: Run
        """
        return (self.category, self.level) == (other.category, other.level)

    def __ne__(self, other) -> bool:
        """
        :type other: Run
        """
        return not (self == other)

    def __hash__(self):
        return hash((self.category, self.level))

    def __set_points(self) -> None:
        self._points = 0
        # If the run is an Individual Level, adapt the request url
        lvl_cat_str = "level/{level}/".format(level=self.level) if self.level else "category/"
        url = "https://www.speedrun.com/api/v1/leaderboards/{game}/" \
              "{lvl_cat_str}{category}?video-only=true&embed=players".format(
                  game=self.game,
                  lvl_cat_str=lvl_cat_str,
                  category=self.category)
        for var_id, var_value in self.variables.items():
            url += "&var-{id}={value}".format(id=var_id, value=var_value)
        leaderboard = SrcRequest.get_cached_response_or_new(url)

        # CHECK: Avoid useless computation
        if len(leaderboard["data"]["runs"]) < MIN_LEADERBOARD_SIZE:
            return

        previous_time = leaderboard["data"]["runs"][0]["run"]["times"]["primary_t"]
        is_speedrun: bool = False

        # TODO: extract the function for valid runs into a function and use a list map
        # Get a list of all banned players in this leaderboard
        banned_players = []
        for player in leaderboard["data"]["players"]["data"]:
            if player.get("role") == "banned":
                banned_players.append(player["id"])

        # First iteration: build a list of valid runs
        valid_runs = []
        for run in leaderboard["data"]["runs"]:
            value = run["run"]["times"]["primary_t"]

            # Making sure this is a speedrun and not a score leaderboard
            # To avoid false negatives due to missing primary times, stop comparing once we know it's a speedrun
            if not is_speedrun:
                if value < previous_time:
                    break  # Score based leaderboard. No need to keep looking
                elif value > previous_time:
                    is_speedrun: bool = True

            # Check if the run is valid (place > 0 & no banned participant)
            if run["place"] > 0:
                for player in run["run"]["players"]:
                    if player.get("id") in banned_players:
                        break
                else:
                    valid_runs.append(run)

        original_population = len(valid_runs)
        # CHECK: Avoid useless computation and errors
        if not is_speedrun or original_population < MIN_LEADERBOARD_SIZE:
            return

        # Sort and remove last 5%
        # TODO: Why we sorting here?
        valid_runs = sorted(valid_runs[:int(original_population * 0.95) or None],
                            key=lambda r: r["run"]["times"]["primary_t"])

        # CHECK: Full level leaderboards with WR under a minute are ignored
        wr_time = valid_runs[0]["run"]["times"]["primary_t"]
        if wr_time < 60 and not self.level:
            return

        # Find the time that's most often repeated in the leaderboard
        # (after the 80th percentile) and cut off everything after that
        pre_cutoff_worst_time = valid_runs[-1]["run"]["times"]["primary_t"]
        valid_runs = keep_runs_before_soft_cutoff(valid_runs)

        mean, standard_deviation, population = get_probability_terms(valid_runs)

        # CHECK: All runs must not have the exact same time
        if standard_deviation <= 0:
            return

        # Get the +- deviation from the mean
        signed_deviation = mean - self.primary_t
        # Get the deviation from the mean of the worse time as a positive number
        worst_time = valid_runs[-1]["run"]["times"]["primary_t"]
        lowest_deviation = worst_time - mean
        # These three shift the deviations up so that the worse time is now 0
        adjusted_deviation = signed_deviation + lowest_deviation

        # CHECK: The last counted run isn't worth any points
        if adjusted_deviation <= 0:
            return

        # Scale all the adjusted deviations so that the mean is worth 1 but the worse stays 0...
        # using the lowest time's deviation from before the "similar times" fix!
        # (runs not affected by the prior fix won't see any difference)
        adjusted_lowest_deviation = pre_cutoff_worst_time - mean
        normalized_deviation = adjusted_deviation / adjusted_lowest_deviation

        # More people means more accurate relative time and more optimised/hard to reach low times
        # This function would equal 0 if population = MIN_LEADERBOARD_SIZE - 1
        certainty_adjustment = 1 - 1 / (population - MIN_LEADERBOARD_SIZE + 2)
        # Cap the exponent to π
        e_exponent = min(normalized_deviation, pi) * certainty_adjustment
        # Bonus points for long games
        length_bonus = 1 + (wr_time / TIME_BONUS_DIVISOR)

        # Give points, hard cap to 6 character
        self._points = min(exp(e_exponent) * 10 * length_bonus, 999.99)
        # Set category name
        self.category_name = re.sub(
            r"((\d\d)$|Any)",
            r"\1%",
            leaderboard["data"]["weblink"]
            .split('#')[1]
            .replace("_", " ")
            .replace("%2B", "+")
            .title()
        )

        # If the run is an Individual Level and worth looking at, set the level count and name
        if self.level and self._points > 0:
            calc_level_count = (self.level_count or 0) + 1
            # ILs leaderboards with WR under their fraction of a minute are ignored
            if wr_time * calc_level_count < 60:
                self._points = 0
            else:
                self._points /= calc_level_count

        # Set game search data
        self._is_wr_time = wr_time == self.primary_t
        self._mean_time = mean


class User:
    _points: float = 0
    _name: str = ""
    _id: str = ""
    _country_code: Optional[str] = None
    _banned: bool = False
    _point_distribution_str: str = ""

    def __init__(self, id_or_name: str) -> None:
        self._id = id_or_name
        self._name = id_or_name

    def __str__(self) -> str:
        return f"User: <{self._name}, {ceil(self._points * 100) / 100}, {self._id}{'(Banned)' if self._banned else ''}>"

    def set_code_and_name(self) -> None:
        url = "https://www.speedrun.com/api/v1/users/{user}".format(user=self._id)
        infos = SrcRequest.get_cached_response_or_new(url)

        self._id = infos["data"]["id"]
        location = infos["data"]["location"]
        self._country_code = location["country"]["code"] if location else None
        self._name = infos["data"]["names"].get("international")
        japanese_name = infos["data"]["names"].get("japanese")
        if japanese_name:
            self._name += f" ({japanese_name})"
        if infos["data"]["role"] == "banned":
            self._banned = True
            self._points = 0

    def set_points(self, threads_exceptions) -> None:
        counted_runs: List[Run] = []
        kept_for_game_values: List[Run] = []

        def set_points_thread(pb) -> None:
            try:
                pb_subcategory_variables = get_subcategory_variables(pb)

                pb_level_id = pb["level"]["data"]["id"] if pb["level"]["data"] else ""
                pb_level_name = pb["level"]["data"]["name"] if pb["level"]["data"] else ""
                run: Run = Run(pb["id"],
                               pb["times"]["primary_t"],
                               pb["game"]["data"]["id"],
                               pb["game"]["data"]["names"]["international"],
                               pb["category"],
                               pb_subcategory_variables,
                               pb_level_id,
                               pb_level_name,
                               len(pb["game"]["data"]["levels"]["data"]))

                # Set game search data
                run._platform = pb["system"]["platform"]

                # If a category has already been counted, only keep the one that's worth the most.
                # This can happen in leaderboards with coop runs or subcategories.
                if run._points > 0:
                    for i, counted_run in enumerate(counted_runs):
                        if counted_run == run:
                            if run._points > counted_run._points:
                                # If other run was a WR in its sub category, keep for GameValues
                                if counted_run._is_wr_time:
                                    kept_for_game_values.append(counted_run)
                                counted_runs[i] = run
                            # If this run was a WR in its sub category, keep for GameValues
                            else:
                                if run._is_wr_time:
                                    kept_for_game_values.append(run)
                            break
                    else:
                        counted_runs.append(run)

            except UserUpdaterError as exception:
                threads_exceptions.append(exception.args[0])
            except Exception:
                threads_exceptions.append({"error": "Unhandled", "details": traceback.format_exc()})

        self._points = 0
        if self._banned:
            return

        url = "https://www.speedrun.com/api/v1/runs?user={user}&status=verified" \
            "&embed=level,game.levels,game.variables&max={pagesize}" \
            .format(user=self._id, pagesize=200)
        runs: List[BasicJSONType] = SrcRequest.get_paginated_response(url)["data"]
        runs = extract_valid_personal_bests(runs)

        original_runs_count = len(runs)
        if original_runs_count >= MAX_RUNS_COUNT:
            runs = keep_last_full_game_runs(runs, MAX_RUNS_COUNT)

            self._point_distribution_str = f"\nOnly kept the last {len(runs)} runs (out of {original_runs_count})." \
                "\nDue to current limitations with PythonAnywhere and the speedrun.com api, " \
                "fully updating such a user is nearly impossible."

        threads = [Thread(target=set_points_thread, args=(run,))
                   for run in runs]
        start_and_wait_for_threads(threads)

        # Sum up the runs' score
        counted_runs.sort(key=lambda r: r._points, reverse=True)
        run_str_lst: List[Tuple[str, float]] = []
        biggest_str_length: int = 0

        for run in counted_runs:
            self._points += run._points
            run_str = "{game} - {category}{level}".format(
                game=run.game_name,
                category=run.category_name,
                level=f" ({run.level_name})" if run.level_name else "")
            run_pts = ceil((run._points * 100)) / 100
            run_str_lst.append((run_str, run_pts))
            biggest_str_length = max(biggest_str_length, len(run_str))

            # This section is kinda hacked in. Used to allow searching for games by their worth
            # Run should be worth more than 1 point, not be a level and be made by WR holder
            if run._points < 1 or run.level or not run._is_wr_time:
                continue
            GameValues.create_or_update(
                run_id=run.id_,
                game_id=run.game,
                category_id=run.category,
                platform_id=run._platform,
                wr_time=floor(run.primary_t),
                wr_points=floor(run._points),
                mean_time=floor(run._mean_time),
            )
        for run in kept_for_game_values:
            if run._points < 1 or run.level:
                continue
            GameValues.create_or_update(
                run_id=run.id_,
                game_id=run.game,
                category_id=run.category,
                platform_id=run._platform,
                wr_time=floor(run.primary_t),
                wr_points=floor(run._points),
                mean_time=floor(run._mean_time),
            )

        self._point_distribution_str += f"\n{'Game - Category (Level)':<{biggest_str_length}} | Points" \
            f"\n{'-'*biggest_str_length} | ------"
        for run_infos in run_str_lst:
            self._point_distribution_str += f"\n{run_infos[0]:<{biggest_str_length}} | " + \
                f"{run_infos[1]:.2f}".rjust(6, ' ')

        if self._banned:
            self._points = 0  # In case the banned flag has been set mid-thread
