import unittest

from pydantic import ValidationError

from app.schemas.life_item import LifeItemCreate, LifeItemKind, LifeItemUpdate


class LifeItemSchemaTests(unittest.TestCase):
    def test_meal_requires_calories_and_offset_aware_occurrence(self):
        with self.assertRaises(ValidationError):
            LifeItemCreate(kind="meal", title="Lunch", occurred_at="2026-10-18T12:00:00+05:30")
        meal = LifeItemCreate(
            kind="meal", title="Lunch", calories=620,
            occurred_at="2026-10-18T12:00:00+05:30", meal_type="Lunch",
        )
        self.assertEqual(meal.calories, 620)
        macros = LifeItemCreate(
            kind="meal", title="Lunch", calories=620, sugar_g=12.5, fat_g=18.2,
            occurred_at="2026-10-18T12:00:00+05:30", meal_type="Lunch",
        )
        self.assertEqual(macros.sugar_g, 12.5)
        self.assertEqual(macros.fat_g, 18.2)
        with self.assertRaises(ValidationError):
            LifeItemCreate(
                kind="meal", title="Lunch", calories=-1, occurred_at="2026-10-18T12:00:00",
                meal_type="Lunch",
            )
        with self.assertRaises(ValidationError):
            LifeItemCreate(
                kind="task", title="Walk", due_at="2026-10-18T12:00:00+05:30",
                sugar_g=2,
            )

    def test_weight_requires_positive_measurement_and_time(self):
        with self.assertRaises(ValidationError):
            LifeItemCreate(kind="weight", title="Weight check-in", weight_kg=0, occurred_at="2026-10-18T12:00:00+05:30")
        with self.assertRaises(ValidationError):
            LifeItemCreate(kind="weight", title="Weight check-in", weight_kg=65, occurred_at="2026-10-18T12:00:00")
        self.assertEqual(
            LifeItemCreate(kind="weight", title="Weight check-in", weight_kg=65, occurred_at="2026-10-18T12:00:00+05:30").kind,
            LifeItemKind.WEIGHT,
        )

    def test_task_and_event_reminder_must_precede_due_time(self):
        task = LifeItemCreate(kind="task", title="Submit report", due_at="2026-10-18T12:00:00+05:30")
        self.assertEqual(task.kind, LifeItemKind.TASK)
        with self.assertRaises(ValidationError):
            LifeItemCreate(
                kind="event", title="Team dinner", starts_at="2026-10-18T12:00:00+05:30",
                reminder_at="2026-10-18T12:00:00+05:30",
            )
        event = LifeItemCreate(
            kind="event", title="Team dinner", starts_at="2026-10-18T12:00:00+05:30",
            reminder_at="2026-10-18T11:50:00+05:30",
        )
        self.assertEqual(event.kind, LifeItemKind.EVENT)

    def test_updates_must_supply_a_non_null_field(self):
        for values in ({}, {"completed": None}, {"title": None}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                LifeItemUpdate(**values)
        self.assertEqual(LifeItemUpdate(completed=True).completed, True)


if __name__ == "__main__":
    unittest.main()
