"""Guard search-page interpretation against the pinned handler response bounds."""
import unittest
from lab import interpret_page


def page(size):
    return {
        'rows': [
            {'id': f'synthetic:{n}', 'fields': {'dtype': 'org', 'dataset': 'book-public'}}
            for n in range(size)
        ],
        'bookmark': 'opaque',
    }


class PinnedPageLimitTests(unittest.TestCase):
    def test_empty_page_ends_without_error(self):
        self.assertEqual(interpret_page({'rows': []}), ([], None))

    def test_one_row_is_preserved(self):
        hits, bookmark = interpret_page(page(1))
        self.assertEqual([hit.identity for hit in hits], ['synthetic:0'])
        self.assertEqual(bookmark, 'opaque')

    def test_authenticated_handler_maximum_100_is_admitted(self):
        hits, _ = interpret_page(page(100))
        self.assertEqual(len(hits), 100)

    def test_first_out_of_contract_page_size_101_rejected(self):
        with self.assertRaisesRegex(ValueError, 'page row budget'):
            interpret_page(page(101))

    def test_oversize_is_rejected_before_row_decoding(self):
        response = page(101)
        response['rows'][0] = {'fields': {}}
        with self.assertRaisesRegex(ValueError, 'page row budget'):
            interpret_page(response)

    def test_oversize_does_not_turn_into_silent_truncation(self):
        with self.assertRaisesRegex(ValueError, 'page row budget'):
            interpret_page(page(250))


if __name__ == '__main__':
    unittest.main()
