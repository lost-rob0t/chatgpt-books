import unittest

from reconcile import EvidenceRow, LedgerError, reconcile, validate_rows


def rows(*statuses: str) -> tuple[EvidenceRow, ...]:
    return tuple(
        EvidenceRow(offset=index, document_id=f"starintel:demo:{index}", status=status)
        for index, status in enumerate(statuses)
    )


class ReconciliationTests(unittest.TestCase):
    def test_verified_prefix_and_absent_suffix_yields_resume_boundary(self):
        result = reconcile(rows("verified_match", "verified_match", "absent", "absent"))
        self.assertEqual(result.state, "verified_prefix_absent_suffix")
        self.assertEqual(result.verified_prefix_count, 2)
        self.assertEqual(result.safe_resume_offset, 2)

    def test_fully_verified_batch_needs_no_replay(self):
        result = reconcile(rows("verified_match", "verified_match"))
        self.assertEqual(result.state, "fully_verified")
        self.assertIsNone(result.safe_resume_offset)
        self.assertIsNone(result.first_unverified_offset)

    def test_absent_entire_batch_can_resume_from_zero(self):
        result = reconcile(rows("absent", "absent", "absent"))
        self.assertEqual(result.state, "verified_prefix_absent_suffix")
        self.assertEqual(result.safe_resume_offset, 0)

    def test_unknown_blocks_mechanical_replay_boundary(self):
        result = reconcile(rows("verified_match", "unknown", "absent"))
        self.assertEqual(result.state, "requires_manual_reconciliation")
        self.assertIsNone(result.safe_resume_offset)

    def test_content_mismatch_blocks_mechanical_replay_boundary(self):
        result = reconcile(rows("verified_match", "mismatch", "absent"))
        self.assertEqual(result.state, "requires_manual_reconciliation")
        self.assertIsNone(result.safe_resume_offset)

    def test_verified_row_after_absence_is_not_treated_as_prefix(self):
        result = reconcile(rows("verified_match", "absent", "verified_match"))
        self.assertEqual(result.state, "requires_manual_reconciliation")
        self.assertIsNone(result.safe_resume_offset)

    def test_offsets_must_be_complete_and_ordered(self):
        malformed = (
            EvidenceRow(0, "starintel:demo:0", "verified_match"),
            EvidenceRow(2, "starintel:demo:2", "absent"),
        )
        with self.assertRaises(LedgerError):
            validate_rows(malformed)

    def test_document_ids_must_be_unique(self):
        malformed = (
            EvidenceRow(0, "starintel:demo:duplicate", "verified_match"),
            EvidenceRow(1, "starintel:demo:duplicate", "absent"),
        )
        with self.assertRaises(LedgerError):
            validate_rows(malformed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
