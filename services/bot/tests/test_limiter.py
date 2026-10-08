from fsp_bot.limiter import SendLimiter, TokenBucket


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept: list[float] = []

    def __call__(self):
        return self.t

    async def sleep(self, s: float):
        self.slept.append(s)
        self.t += s


async def test_bucket_blocks_after_burst():
    c = Clock()
    b = TokenBucket(2, 2, clock=c, sleep=c.sleep)
    for _ in range(2):
        await b.acquire()
    assert c.slept == []
    await b.acquire()
    assert c.slept == [0.5]


async def test_one_message_per_second_per_chat_but_other_chats_free():
    c = Clock()
    lim = SendLimiter(25, 1, clock=c, sleep=c.sleep)
    await lim.acquire(1)
    await lim.acquire(2)
    assert c.slept == []
    await lim.acquire(1)
    assert sum(c.slept) >= 0.99


async def test_global_limit_25_per_second():
    c = Clock()
    lim = SendLimiter(25, 1, clock=c, sleep=c.sleep)
    for chat in range(100):
        await lim.acquire(chat)
    # 25 в корзине сразу, остальные 75 — по 25/с
    assert 2.9 <= c.t <= 3.1
