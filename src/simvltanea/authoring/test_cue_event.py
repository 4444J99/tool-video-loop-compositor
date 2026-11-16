"""The ``cue`` event: one event pins a loop to a named clip (issue #71 item 4).

A cue-encoded state shows exactly what the reroll-encoded state of the same schedule shows, with about one event
per clip change; a state that does not use it keeps engine 1.0.0 and its bytes; engines that do not know 1.2.0
refuse it by name.
"""
import copy
import unittest

from simvltanea.authoring import composition as c
from simvltanea.authoring import play_engine as pe
from simvltanea.authoring.play_config import PlayError, validate_config
from simvltanea.authoring.test_gravity_pool import make_pool
from simvltanea.authoring.test_play_support import FPS, digest

POOL = make_pool(60)


def play(n, seconds, seed, events, **kwargs):
    config = {"encoding": {"events": events}}
    for key, value in kwargs.items():
        config.setdefault("path", {})[key] = value
    return pe.schedule_play(POOL, n, config, seconds, FPS, seed)


class CueEncodingTests(unittest.TestCase):
    def test_a_cue_state_shows_what_the_reroll_state_shows_at_every_frame(self):
        for n, seconds, seed in ((3, 45, 1), (5, 60, "cue-seed"), (4, 40, 9)):
            with self.subTest(n=n, seed=seed):
                reroll = play(n, seconds, seed, "reroll")["state"]
                cue = play(n, seconds, seed, "cue")["state"]
                frames = sorted({0, reroll["frames"] - 1, *(e["frame"] for e in reroll["events"]),
                                 *(e["frame"] + 1 for e in reroll["events"] if e["frame"] + 1 < reroll["frames"])})
                for frame in frames:
                    got = {x["id"]: x["source"] for x in c.resolve_at(cue, frame)["loops"]}
                    want = {x["id"]: x["source"] for x in c.resolve_at(reroll, frame)["loops"]}
                    self.assertEqual(got, want, frame)

    def test_a_cue_state_is_far_shorter_and_carries_the_cue_engine_version(self):
        reroll = play(5, 60, 2, "reroll")
        cue = play(5, 60, 2, "cue")
        self.assertEqual(cue["state"]["engine_version"], c.CUE_ENGINE_VERSION)
        self.assertEqual(cue["state"]["engine_version"], "1.2.0")
        ops = {e["op"] for e in cue["state"]["events"]}
        self.assertEqual(ops - {"swap"}, {"cue"})
        shows = sum(ch["op"] == "show" for ch in cue["schedule"].changes)
        self.assertEqual(sum(e["op"] == "cue" for e in cue["state"]["events"]), shows)
        self.assertLess(len(cue["state"]["events"]), len(reroll["state"]["events"]))
        c.validate_state(cue["state"])

    def test_the_default_encoding_is_unchanged_and_keeps_engine_1_0_0(self):
        default = pe.schedule_play(POOL, 4, None, 30, FPS, 5)["state"]
        explicit = play(4, 30, 5, "reroll")["state"]
        self.assertEqual(default["engine_version"], c.ENGINE_VERSION)
        self.assertEqual(digest(default), digest(explicit))
        self.assertTrue(all(e["op"] != "cue" for e in default["events"]))
        self.assertEqual(validate_config(None)["encoding"], {"events": "reroll"})

    def test_an_unknown_encoding_is_refused(self):
        with self.assertRaises(PlayError):
            validate_config({"encoding": {"events": "teleport"}})

    def test_a_cue_state_with_swaps_matches_the_reroll_state(self):
        reroll = pe.schedule_play(POOL, 5, {"timing": {"swap_interval": 15}}, 60, FPS, 3)["state"]
        cue = pe.schedule_play(POOL, 5, {"timing": {"swap_interval": 15}, "encoding": {"events": "cue"}}, 60, FPS, 3)["state"]
        if not any(e["op"] == "swap" for e in cue["events"]):
            self.skipTest("this configuration produced no swap")
        for frame in sorted({0, *(e["frame"] for e in reroll["events"])}):
            self.assertEqual({x["id"]: x["source"] for x in c.resolve_at(cue, frame)["loops"]},
                             {x["id"]: x["source"] for x in c.resolve_at(reroll, frame)["loops"]}, frame)


class CueValidationTests(unittest.TestCase):
    def setUp(self):
        self.state = play(3, 30, 4, "cue")["state"]

    def refuse(self, state, text):
        with self.assertRaises(c.StateError) as caught:
            c.validate_state(state)
        self.assertIn(text, str(caught.exception))

    def test_engine_1_0_0_refuses_a_cue_event_by_name(self):
        state = copy.deepcopy(self.state)
        state["engine_version"] = c.ENGINE_VERSION
        self.refuse(state, "unsupported event: cue")

    def test_a_cue_must_name_a_source_of_the_state(self):
        state = copy.deepcopy(self.state)
        event = next(e for e in state["events"] if e["op"] == "cue")
        event["source"] = "no-such-clip"
        self.refuse(state, "cue references absent source")

    def test_a_cue_must_name_a_loop_of_the_state(self):
        state = copy.deepcopy(self.state)
        next(e for e in state["events"] if e["op"] == "cue")["loop"] = "loop-99"
        self.refuse(state, "event references absent loop")

    def test_a_cue_with_an_extra_or_missing_field_is_refused(self):
        for mutate in (lambda e: e.pop("source"), lambda e: e.update(value=True)):
            state = copy.deepcopy(self.state)
            mutate(next(e for e in state["events"] if e["op"] == "cue"))
            with self.assertRaises(c.StateError):
                c.validate_state(state)

    def test_the_cue_version_is_only_for_schema_1(self):
        state = copy.deepcopy(self.state)
        state["schema_version"] = c.AUDIO_SCHEMA_VERSION
        with self.assertRaises(c.StateError):
            c.validate_state(state)


if __name__ == "__main__":
    unittest.main()
