import unittest
from cadence.placement import snap_origin

AREA = (0, 0, 1440, 860)
SIZE = (680, 340)


class PlacementTests(unittest.TestCase):
    def test_snaps_to_centre_and_edges_when_close(self):
        self.assertEqual(snap_origin((372, 268), SIZE, AREA), (380, 260))
        self.assertEqual(snap_origin((8, 500), SIZE, AREA), (16, 504))
        self.assertEqual(snap_origin((750, 10), SIZE, AREA), (744, 16))

    def test_leaves_other_positions_alone(self):
        self.assertEqual(snap_origin((200, 120), SIZE, AREA), (200, 120))
        self.assertEqual(snap_origin((380, 260), SIZE, AREA), (380, 260))

    def test_uses_the_screen_the_widget_is_on(self):
        self.assertEqual(snap_origin((1830, 265), SIZE, (1440, 0, 1440, 860)), (1820, 260))
