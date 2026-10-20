import unittest
from merge_logic import merge_state


def state(events=None, tasks=None, changes=None):
    return {"events": events or [], "tasks": tasks or [], "assets": [], "changes": changes or []}


class MergeLogicTests(unittest.TestCase):
    def test_different_fields_merge_without_conflict(self):
        base = state(events=[{"id":"e1","title":"A","place":"Hall"}])
        current = state(events=[{"id":"e1","title":"A","place":"Room B"}])
        incoming = state(events=[{"id":"e1","title":"B","place":"Hall"}])
        merged, conflicts = merge_state(base, current, incoming)
        self.assertEqual([], conflicts)
        self.assertEqual({"id":"e1","title":"B","place":"Room B"}, merged["events"][0])

    def test_same_field_conflict_preserves_server_value(self):
        base = state(events=[{"id":"e1","title":"A","place":"Hall"}])
        current = state(events=[{"id":"e1","title":"A","place":"Room B"}])
        incoming = state(events=[{"id":"e1","title":"A","place":"Room C"}])
        merged, conflicts = merge_state(base, current, incoming)
        self.assertEqual("Room B", merged["events"][0]["place"])
        self.assertEqual("events[e1].place", conflicts[0]["path"])

    def test_concurrent_additions_both_survive(self):
        base = state(events=[{"id":"e1","title":"A"}])
        current = state(events=[{"id":"e1","title":"A"},{"id":"e2","title":"B"}])
        incoming = state(events=[{"id":"e1","title":"A"},{"id":"e3","title":"C"}])
        merged, conflicts = merge_state(base, current, incoming)
        self.assertEqual([], conflicts)
        self.assertEqual({"e1","e2","e3"}, {x["id"] for x in merged["events"]})

    def test_unrelated_fields_save_even_when_one_field_conflicts(self):
        base = state(events=[{"id":"e1","title":"A","place":"Hall"}], tasks=[{"id":"t1","name":"LED","status":"待确认"}])
        current = state(events=[{"id":"e1","title":"A","place":"Room B"}], tasks=[{"id":"t1","name":"LED","status":"待确认"}])
        incoming = state(events=[{"id":"e1","title":"A","place":"Room C"}], tasks=[{"id":"t1","name":"LED","status":"制作中"}])
        merged, conflicts = merge_state(base, current, incoming)
        self.assertEqual("Room B", merged["events"][0]["place"])
        self.assertEqual("制作中", merged["tasks"][0]["status"])
        self.assertEqual(1, len(conflicts))

if __name__ == "__main__":
    unittest.main()
