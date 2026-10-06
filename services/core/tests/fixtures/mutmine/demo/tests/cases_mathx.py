"""Тесты проекта-фикстуры: только данные для майнинга, pytest их не собирает и не запускает."""

import unittest

from pkg.mathx import binary_search, is_palindrome


def test_binary_search():
    assert binary_search([1, 3, 5, 7, 9], 7) == 3
    assert binary_search([1, 3, 5, 7, 9], 1) == 0
    assert binary_search([1, 3, 5, 7, 9], 9) == 4
    assert binary_search([1, 3, 5, 7, 9], 4) == -1
    assert binary_search([], 1) == -1


class PalindromeTest(unittest.TestCase):
    def test_yes(self):
        self.assertTrue(is_palindrome("Level"))
        self.assertEqual(is_palindrome("abba"), True)

    def test_no(self):
        self.assertFalse(is_palindrome("abca"))
        self.assertEqual(is_palindrome("ab"), False)
