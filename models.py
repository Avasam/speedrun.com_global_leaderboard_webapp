#!/usr/bin/python
# -*- coding: utf-8 -*-

##########################################################################
# Ava's Global Speedrunning Scoreboard
# Copyright (C) 2018 Samuel Therrien
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Contact:
# samuel.06@hotmail.com
##########################################################################
from __future__ import annotations
from flask_login import login_user
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from typing import Union
from utils import get_file, SpeedrunComError
import traceback

db = SQLAlchemy()

friend = db.Table(
    'friend',
    db.Column(
        'user_id',
        db.String(8),
        db.ForeignKey('player.user_id')),
    db.Column(
        'friend_id',
        db.String(8),
        db.ForeignKey('player.user_id'))
)


class Player(db.Model, UserMixin):
    __tablename__ = "player"

    user_id: str = db.Column(db.String(8), primary_key=True)
    name: str = db.Column(db.String(32), nullable=False)
    score: int = db.Column(db.Integer, nullable=False)
    last_update = db.Column(db.DateTime())

    @staticmethod
    def authenticate(api_key: str):
        print(api_key)
        try:  # Get user from speedrun.com using the API key
            user_id: Union[str, None] = get_file(
                "https://www.speedrun.com/api/v1/profile", {"X-API-Key": api_key})["data"]["id"]
            print("user_id = ", user_id)
        except SpeedrunComError:
            print("\nError: Unknown\n{}".format(traceback.format_exc()))
            return None
            # TODO: return json.dumps({'state': 'warning', 'message': 'Invalid API key.'})
        except Exception:
            print("\nError: Unknown\n{}".format(traceback.format_exc()))
            return None
            # TODO: return json.dumps({"state": "danger", "message": traceback.format_exc()})

        if not user_id:  # Confirms wether the API key is valid
            return None
            # TODO: return json.dumps({'state': 'warning', 'message': 'Invalid API key.'})

        # TODO: optionally update that user
        player: Player = Player.get(user_id)

        if not player:
            return None
            # TODO: Add user to DB and load them in

        login_user(player)  # Login for non SPA

        return player

    @staticmethod
    def get(id: str) -> Player:
        return Player.query.get(id)

    @staticmethod
    def get_all():
        sql = text("SELECT *, rank FROM ( "
                   "    SELECT *, "
                   "        IF(score = @_last_score, @cur_rank := @cur_rank, @cur_rank := @_sequence) AS rank, "
                   "        @_sequence := @_sequence + 1, "
                   "        @_last_score := score "
                   "    FROM player, (SELECT @cur_rank := 1, @_sequence := 1, @_last_score := NULL) r "
                   "    ORDER BY score DESC "
                   ") ranked;")
        return db.engine.execute(sql).fetchall()

    def get_friends(self):
        sql = text("SELECT DISTINCT friend_id FROM friend "
                   "WHERE friend.user_id = '{user_id}';".format(
                       user_id=self.user_id))
        return [friend_id[0] for friend_id in db.engine.execute(sql).fetchall()]

    def befriend(self, friend_id: str) -> bool:
        if self.user_id == friend_id:
            return False
        sql = text("INSERT INTO friend (user_id, friend_id) "
                   "VALUES ('{user_id}', '{friend_id}');".format(
                       user_id=self.user_id,
                       friend_id=friend_id))
        return db.engine.execute(sql)

    def unfriend(self, friend_id: str) -> Union[bool]:
        sql = text("DELETE FROM friend "
                   "WHERE user_id = '{user_id}' AND friend_id = '{friend_id}';".format(
                       user_id=self.user_id,
                       friend_id=friend_id))
        return db.engine.execute(sql)

    # Override from UserMixin for Flask-Login
    def get_id(self):
        return self.user_id