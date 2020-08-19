from __future__ import annotations
from datetime import datetime, timedelta
from math import ceil, exp, floor, pi
from models.game_search_models import GameValues
from services.utils import get_file, UserUpdaterError
from threading import Thread, active_count
from time import sleep
from typing import Dict, List, Optional, Tuple
import configs
import re
import traceback

MIN_LEADERBOARD_SIZE = 3  # This is just to optimize as the formula gives 0 points to leaderboards size < 3
TIME_BONUS_DIVISOR = 3600 * 12  # 12h (1/2 day) for +100%
GAMETYPE_MULTI_GAME = "rj1dy1o8"

memoized_requests: Dict[str, CachedRequest] = {}


class CachedRequest():
    global memoized_requests
    result: dict
    timestamp: datetime

    def __init__(self, result: dict, timestamp: datetime):
        self.result = result
        self.timestamp = timestamp

    @staticmethod
    def get_response_or_new(url: str) -> dict:
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
            memoized_requests[url] = CachedRequest(result, today)
            return result


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
            category: str,
            variables=None,
            level: str = "",
            level_name: str = "",
            level_count: int = 0):
        self.id_ = id_
        self.primary_t = primary_t
        self.game = game
        self.game_name = game
        self.category = category
        self.category_name = category
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
        leaderboard = CachedRequest.get_response_or_new(url)

        if len(leaderboard["data"]["runs"]) >= MIN_LEADERBOARD_SIZE:  # Check to avoid useless computation
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
            if is_speedrun and original_population >= MIN_LEADERBOARD_SIZE:  # Avoid useless computation and errors
                # Sort and remove last 5%
                # TODO: Why we sorting here?
                valid_runs = sorted(valid_runs[:int(original_population * 0.95) or None],
                                    key=lambda r: r["run"]["times"]["primary_t"])

                # TODO: This is not optimized
                pre_fix_worst_time = valid_runs[-1]["run"]["times"]["primary_t"]
                # TODO: Extract "cutoff everything after soft cutoff" to its own function
                # Find the time that's most often repeated in the leaderboard (after the 80th percentile)
                # and cut off everything after that
                cut_off_80th_percentile: int = valid_runs[int(len(valid_runs)*0.8)]["run"]["times"]["primary_t"]
                count: int = 0
                most_repeated_time_pos: int = 0
                most_repeated_time_count: int = 0
                last_value: int = 0
                i: int = len(valid_runs)
                # Go in reverse this way we can break at the percentile
                for run in reversed(valid_runs):
                    value: int = run["run"]["times"]["primary_t"]
                    if value == last_value:
                        count += 1
                    else:
                        if count >= most_repeated_time_count:
                            most_repeated_time_count = count
                            most_repeated_time_pos = i
                        count = 0
                    last_value = value

                    # We hit the 80th percentile, there's no more to be analyzed
                    # If the most repeated time IS the 80th percentile, still remove it (< not <=)
                    if value < cut_off_80th_percentile:
                        # Have the most repeated time repeat at least a certain amount
                        if most_repeated_time_count > MIN_LEADERBOARD_SIZE:
                            # Actually keep the last one (+1) as it'll be worth 0 points and used for other calculations
                            del valid_runs[most_repeated_time_pos+1:]
                        break
                    i -= 1

                # Second iteration: maths!
                mean: float = 0.0
                sigma: float = 0.0
                population: int = 0
                for run in valid_runs:
                    value = run["run"]["times"]["primary_t"]
                    population += 1
                    mean_temp = mean
                    mean += (value - mean_temp) / population
                    sigma += (value - mean_temp) * (value - mean)

                # Full level leaderboards with mean under a minute are ignored
                if mean < 60 and not self.level:
                    return
                self._mean_time = mean

                wr_time = valid_runs[0]["run"]["times"]["primary_t"]

                standard_deviation = (sigma / population) ** 0.5
                if standard_deviation > 0:  # All runs must not have the exact same time
                    # Get the +- deviation from the mean
                    signed_deviation = mean - self.primary_t
                    # Get the deviation from the mean of the worse time as a positive number
                    worst_time = valid_runs[-1]["run"]["times"]["primary_t"]
                    lowest_deviation = worst_time - mean
                    # These three shift the deviations up so that the worse time is now 0
                    adjusted_deviation = signed_deviation + lowest_deviation
                    if adjusted_deviation > 0:  # The last counted run isn't worth any points
                        # Scale all the adjusted deviations so that the mean is worth 1 but the worse stays 0...
                        # using the lowest time's deviation from before the "similar times" fix!
                        # (runs not affected by the prior fix won't see any difference)
                        adjusted_lowest_deviation = pre_fix_worst_time - mean
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
                        # Set names
                        game_category = re.split(
                            "[/#]",
                            leaderboard["data"]["weblink"][leaderboard["data"]["weblink"].rindex("com/") + 4:]
                            .replace("_", " ")
                            .title())
                        self.game_name = game_category[0]  # Always first of 2-3 items
                        self.category_name = game_category[-1]  # Always last of 2-3 items

                        # If the run is an Individual Level and worth looking at, set the level count and name
                        if self.level and self._points > 0:
                            self.level_name = game_category[1]  # Always 2nd of 3 items
                            calc_level_count = (self.level_count or 0) + 1
                            # ILs leaderboards with mean under their fraction of a minute are ignored
                            if mean * calc_level_count < 60:
                                self._points = 0
                            else:
                                self._points /= calc_level_count


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
        infos = CachedRequest.get_response_or_new(url)

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
                # Get a list of the game's subcategory variables
                game_subcategory_ids: List[str] = []
                for game_variable in pb["game"]["data"]["variables"]["data"]:
                    if game_variable["is-subcategory"]:
                        game_subcategory_ids.append(game_variable["id"])

                pb_subcategory_variables: Dict[str, Dict[str, str]] = {}
                # For every variable in the run...
                for pb_var_id, pb_var_value in pb["run"]["values"].items():
                    # ...find if said variable is one of the game's subcategories...
                    if pb_var_id in game_subcategory_ids:
                        # ... and add it to the run's subcategory variables
                        pb_subcategory_variables[pb_var_id] = pb_var_value

                pb_level_name = pb["level"]["data"]["name"] if len(pb["level"]["data"]) > 0 else ""
                run: Run = Run(pb["run"]["id"],
                               pb["run"]["times"]["primary_t"],
                               pb["run"]["game"],
                               pb["run"]["category"],
                               pb_subcategory_variables,
                               pb["run"]["level"],
                               pb_level_name,
                               len(pb["game"]["data"]["levels"]["data"]))

                # Set game search data
                run._is_wr_time = pb["place"] == 1
                run._platform = pb["run"]["system"]["platform"]

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

        if not self._banned:
            url = \
                "https://www.speedrun.com/api/v1/users/{user}/personal-bests?embed=level,game.levels,game.variables" \
                .format(user=self._id)
            pbs = CachedRequest.get_response_or_new(url)

            # TODO: BIG MEGA HACK / PATCH. Let's try to work around this issue ASAP.
            runs_count = len(pbs["data"])
            if runs_count >= 1000:
                raise UserUpdaterError({
                    "error": "Too Many Runs",
                    "details": f"{self._name} has over 1000 runs ({runs_count} to be exact). " +
                    "Due to current limitations with PythonAnywhere and the speedrun.com api, " +
                    "updating such a user is nearly impossible. " +
                    "I have a work in progress solution for this issue, but it will take time. " +
                    "Sorry for the inconvenience.",
                })

            self._points = 0
            threads: List[Thread] = []
            for pb in pbs["data"]:
                # Check if it's a valid run:
                # - not a "multi-game" gametype
                # - has a category
                # - has video verification
                if GAMETYPE_MULTI_GAME not in pb["game"]["data"]["gametypes"] \
                        and pb["run"]["category"] \
                        and pb["run"].get("videos"):
                    threads.append(Thread(target=set_points_thread, args=(pb,)))
            for t in threads:
                while True:
                    try:
                        if active_count() <= 8:
                            t.start()
                            break
                    except RuntimeError:
                        print(
                            f"RuntimeError: Can't start {active_count()+1}th thread. "
                            f"Trying to wait just a bit as I don't have a better way to deal w/ it atm.")
                        sleep(0.5)
            for t in threads:
                t.join()

            # Sum up the runs' score
            counted_runs.sort(key=lambda r: r._points, reverse=True)
            run_str_lst: List[Tuple[str, float]] = []
            biggest_str_length: int = 0

            for run in counted_runs:
                self._points += run._points
                run_str = ("{game} - {category}{level}".format(game=run.game_name,
                                                               category=run.category_name,
                                                               level=f" ({run.level_name})" if run.level_name else ""))
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

            self._point_distribution_str = f"\n{'Game - Category (Level)':<{biggest_str_length}} | Points" \
                                           f"\n{'-'*biggest_str_length} | ------"
            for run_infos in run_str_lst:
                self._point_distribution_str += f"\n{run_infos[0]:<{biggest_str_length}} | " + \
                    f"{run_infos[1]:.2f}".rjust(6, ' ')

            if self._banned:
                self._points = 0  # In case the banned flag has been set mid-thread
        else:
            self._points = 0
