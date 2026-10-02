"""Состояния FSM (telegram.md §3). Хранилище — RedisStorage (`fsm:*`), TTL 30 минут."""

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    consents = State()


class Resume(StatesGroup):
    awaiting_file = State()


class Fsp(StatesGroup):
    awaiting_id = State()
    awaiting_code = State()


class Github(StatesGroup):
    awaiting_login = State()


class Test(StatesGroup):
    in_progress = State()  # id сессии — в данных FSM


class Offer(StatesGroup):
    awaiting_question = State()  # offer_id — в данных FSM


class Interview(StatesGroup):
    answering = State()  # id и номер вопроса — в данных FSM


class Settings(StatesGroup):
    awaiting_salary = State()
