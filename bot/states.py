from aiogram.fsm.state import State, StatesGroup


class New(StatesGroup):
    describing = State()   # collecting the idea text, possibly over several messages
    profile = State()      # place / local / online - data: raw
    mode = State()         # data: raw, profile


class Fix(StatesGroup):
    typing = State()       # data: idea_id, step_key


class Ask(StatesGroup):
    typing = State()       # data: qid, idea_id - free-text answer to a micro-survey question
