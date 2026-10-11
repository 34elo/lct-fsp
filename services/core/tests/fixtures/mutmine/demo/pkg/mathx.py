"""Учебный модуль-фикстура для майнинга мутаций. Не импортируется тестами core."""


def count_greater(items, limit):
    """Count items strictly greater than limit.

    >>> count_greater([1, 5, 7, 3], 4)
    2
    >>> count_greater([], 0)
    0
    """
    total = 0
    for x in items:
        if x > limit:
            total += 1
    return total


def max_value(values):
    """Largest element of a non-empty list.

    >>> max_value([-3, -1, -7])
    -1
    >>> max_value([4, 9, 2])
    9
    >>> max_value([])
    Traceback (most recent call last):
    ...
    ValueError: empty
    """
    if not values:
        raise ValueError("empty")
    best = values[0]
    for v in values[1:]:
        if v > best:
            best = v
    return best


def binary_search(xs, target):
    """Index of target in sorted xs or -1."""
    lo, hi = 0, len(xs) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if xs[mid] == target:
            return mid
        if xs[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def is_palindrome(s):
    """True if s reads the same both ways, ignoring case."""
    t = s.lower()
    i, j = 0, len(t) - 1
    while i < j:
        if t[i] != t[j]:
            return False
        i += 1
        j -= 1
    return True


def factorial(n):
    """n! for n >= 0.

    >>> factorial(0)
    1
    >>> factorial(5)
    120
    """
    if n <= 1:
        return 1
    return n * factorial(n - 1)


def word_lengths(text):
    """Lengths of words longer than two letters.

    >>> word_lengths("a bb ccc dddd")
    {'ccc': 3, 'dddd': 4}
    """
    return {w: len(w) for w in text.split() if len(w) > 2}


def forever(n):
    """Mutants of this loop may hang: the sandbox step limit must stop them.

    >>> forever(3)
    6
    >>> forever(0)
    0
    """
    s = 0
    while n > 0:
        s += n
        n -= 1
    return s
