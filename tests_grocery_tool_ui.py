"""Isolated Tk checks for the grocery tool. No worker or game APIs are used."""
import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest

from grocery_tool_ui import GroceryToolView, ROOT, SHOP_LABELS
from grocery_plan import new_state, save_state


class FakeController:
    def __init__(self, ui, view, root):
        self.ui, self.view, self.root = ui, view, root
        self.running = False
        self.starts = []
        self.stops = 0
        self.observations = 0

    def start(self, new_round=False):
        if self.ui.running or self.running:
            self.view.show_status('已有任务运行')
            return
        self.starts.append((new_round, self.view.validated_quantities()))
        self.running = True
        self.view.set_running(True)

    def stop(self):
        self.stops += 1
        self.running = False
        self.view.set_running(False)

    def observe(self):
        self.observations += 1


class GroceryToolUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='grocery-ui-', dir=ROOT / 'verification')
        self.folder = Path(self.temp.name)
        self.ui = tk.Tk()
        self.ui.geometry('1000x700+10000+10000')
        self.ui.running = False
        self.view = GroceryToolView(self.ui, self.ui, root=self.folder, controller_factory=FakeController)
        self.view.pack(fill='both', expand=True)
        self.ui.update()

    def tearDown(self):
        for job in self.ui.tk.call('after', 'info'):
            self.ui.after_cancel(job)
        self.ui.destroy()
        self.temp.cleanup()

    def test_all_four_shops_have_correct_names_icons_and_quantities(self):
        self.assertEqual(len(self.view.variables), 141)
        self.assertEqual(len(self.view.photos), 97)
        self.assertEqual({shop: len(cards) for shop, cards in self.view.shop_cards.items()},
                         {'sun': 25, 'moon': 38, 'sign': 61, 'mystery': 17})
        for item in self.view.catalog:
            with self.subTest(item=item['name']):
                key = item['key']
                self.assertEqual(self.view.variables[key].get(), '0')
                labels = [child for child in self.view.cards[key].winfo_children() if isinstance(child, tk.Label)]
                self.assertIn(item['name'], [child.cget('text') for child in labels])
                images = [child for child in labels if child.cget('image')]
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0].cget('image'), str(self.view.photos[item['asset']]))
                # The number input is below its icon in the actual widget grid.
                self.assertGreater(int(self.view.inputs[key].grid_info()['row']), int(images[0].grid_info()['row']))
        self.assertFalse(self.view.plan_path.exists(), 'Opening the tool must not create a preset')

    def test_repeated_gift_asset_does_not_share_quantity_variables(self):
        duplicates = [item for item in self.view.catalog if item['shop'] == 'sign' and item['asset'] == 'item_10100000']
        self.assertEqual(len(duplicates), 36)
        keys = [item['key'] for item in duplicates]
        self.assertEqual(len(set(keys)), 36)
        self.view.variables[keys[0]].set('5')
        self.view._autosave()
        self.assertTrue(all(self.view.variables[key].get() == '0' for key in keys[1:]))

    def test_valid_edits_are_saved_and_restored_without_public_configuration(self):
        first, second = self.view.catalog[0]['key'], self.view.catalog[-1]['key']
        self.view.variables[first].set('5')
        self.view.variables[second].set('2')
        self.view._autosave()
        self.assertTrue(self.view.plan_path.exists())
        self.view.destroy()
        self.view = GroceryToolView(self.ui, self.ui, root=self.folder, controller_factory=FakeController)
        self.view.pack(fill='both', expand=True)
        self.ui.update()
        self.assertEqual(self.view.variables[first].get(), '5')
        self.assertEqual(self.view.variables[second].get(), '2')
        self.assertFalse((self.folder / 'config.json').exists())
        self.assertFalse((self.folder / 'run.json').exists())

    def test_invalid_number_is_inline_and_cannot_replace_saved_preset(self):
        key = self.view.catalog[0]['key']
        self.view.variables[key].set('3')
        self.view._autosave()
        before = self.view.plan_path.read_bytes()
        for invalid in ('', '-1', '1.5', 'abc'):
            with self.subTest(value=invalid):
                self.view.variables[key].set(invalid)
                self.view._autosave()
                self.assertTrue(self.view.errors[key].get())
                self.assertEqual(before, self.view.plan_path.read_bytes())
                with self.assertRaises(ValueError):
                    self.view.validated_quantities()

    def test_closing_before_debounce_preserves_a_valid_edit(self):
        key = self.view.catalog[0]['key']
        self.view.variables[key].set('7')
        self.assertFalse(self.view.plan_path.exists())
        self.view.destroy()
        saved = json.loads((self.folder / 'grocery_plan.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['quantities'][key], 7)

    def test_start_stop_and_edit_lock_use_only_the_tool_controller(self):
        key = self.view.catalog[0]['key']
        self.view.variables[key].set('2')
        self.view.start_button.invoke()
        self.assertTrue(self.view.controller.running)
        self.assertEqual(self.view.controller.starts[0][1][key], 2)
        self.assertTrue(all(str(widget.cget('state')) == 'disabled' for widget in self.view.inputs.values()))
        self.assertEqual(str(self.view.stop_button.cget('state')), 'normal')
        self.view.stop_button.invoke()
        self.assertEqual(self.view.controller.stops, 1)
        self.assertTrue(all(str(widget.cget('state')) == 'normal' for widget in self.view.inputs.values()))
        self.view.set_pending_state(True)
        self.assertEqual(self.view.start_button.cget('text'), '继续本轮')
        self.view.new_button.invoke()
        self.assertTrue(self.view.controller.starts[-1][0])

    def test_currencies_use_user_labels_and_keep_last_verified_values(self):
        self.view.show_balance({'sun': 13609, 'moon': 320565, 'sign': 8300, 'mystery': 321}, '2026-10-26 15:00:00')
        self.assertEqual([self.view.balance_vars[k].get() for k in SHOP_LABELS], ['13,609', '320,565', '8,300', '321'])
        self.assertIn('2026-10-26 15:00:00', self.view.balance_time.get())
        self.view.show_balance({'sun': 13559}, '2026-10-26 15:00:01')
        self.assertEqual(self.view.balance_vars['sun'].get(), '13,559')
        self.assertEqual(self.view.balance_vars['moon'].get(), '320,565')

    def test_unverified_purchase_capability_blocks_purchase_but_allows_balance_reading(self):
        self.view.set_purchase_capability(False, '交易确认页面尚无真实证据')
        self.assertIn('自动购买待实机验证', self.view.purchase_notice.get())
        self.assertEqual(str(self.view.start_button.cget('state')), 'disabled')
        self.assertEqual(str(self.view.new_button.cget('state')), 'disabled')
        self.assertEqual(str(self.view.observe_button.cget('state')), 'normal')
        self.view.start_button.invoke()
        self.view.new_button.invoke()
        self.assertEqual(self.view.controller.starts, [])
        self.view.observe_button.invoke()
        self.assertEqual(self.view.controller.observations, 1)
        self.assertFalse(self.view.plan_path.exists())

    def test_balance_reading_is_locked_while_running_and_capability_survives_stop(self):
        self.view.set_purchase_capability(False, '等待实机验证')
        self.view.set_running(True)
        self.assertEqual(str(self.view.observe_button.cget('state')), 'disabled')
        self.view.observe_button.invoke()
        self.assertEqual(self.view.controller.observations, 0)
        self.view.set_running(False)
        self.assertEqual(str(self.view.observe_button.cget('state')), 'normal')
        self.assertEqual(str(self.view.start_button.cget('state')), 'disabled')
        self.assertEqual(str(self.view.new_button.cget('state')), 'disabled')
        self.view.observe_button.invoke()
        self.assertEqual(self.view.controller.observations, 1)

    def test_latest_balance_record_is_not_overwritten_by_an_old_purchase_journal(self):
        catalog = self.view.catalog
        self.view.destroy()
        old = new_state(catalog, {catalog[0]['key']: 1})
        old['status'] = 'stopped'
        old['balances_latest'] = {'sun': 100, 'moon': 200, 'sign': 300, 'mystery': 400}
        old['balances_read_at'] = '2026-10-26T10:00:00+08:00'
        save_state(self.folder / 'grocery_state.json', old)
        latest = {'balances': {'sun': 101, 'moon': 202, 'sign': 303, 'mystery': 404},
                  'read_at': '2026-10-26T11:00:00+08:00'}
        (self.folder / 'grocery_balances.json').write_text(json.dumps(latest), encoding='utf-8')

        class RestoringController(FakeController):
            def __init__(self, ui, view, root):
                super().__init__(ui, view, root)
                record = json.loads((root / 'grocery_balances.json').read_text(encoding='utf-8'))
                view.show_balance(record['balances'], record['read_at'])

        self.view = GroceryToolView(self.ui, self.ui, root=self.folder, controller_factory=RestoringController)
        self.view.pack(fill='both', expand=True)
        self.ui.update()
        self.assertEqual([self.view.balance_vars[key].get() for key in SHOP_LABELS], ['101', '202', '303', '404'])
        self.assertIn(latest['read_at'], self.view.balance_time.get())
        self.assertEqual(self.view.start_button.cget('text'), '继续本轮')

    def test_tabs_shortcuts_and_card_scrolling_do_not_change_the_plan(self):
        for shop, button in self.view.shop_buttons.items():
            button.invoke()
            self.ui.update()
            self.assertEqual(self.view.selected_shop, shop)
        self.view.show_shop('sign')
        canvas = self.view.shop_canvases['sign']
        canvas.yview_moveto(0)
        self.view.shop_cards['sign'][0].event_generate('<MouseWheel>', delta=-120)
        self.ui.update()
        self.assertGreater(canvas.yview()[0], 0)
        self.view.tool_buttons['shortcuts'].invoke()
        self.assertEqual(self.view.selected_tool, 'shortcuts')
        self.assertEqual(len(self.view.shortcut_buttons), 4)
        self.view.tool_buttons['grocery'].invoke()
        self.assertEqual(self.view.selected_tool, 'grocery')
        self.assertFalse(self.view.plan_path.exists())
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        self.assertFalse(any(isinstance(widget, (tk.Scrollbar, ttk.Scrollbar)) for widget in descendants(self.view)))

    def test_responsive_cards_fit_horizontal_viewport(self):
        for width in (700, 1000, 1500):
            with self.subTest(width=width):
                self.ui.geometry(f'{width}x700+10000+10000')
                self.ui.update()
                self.view.show_shop('sun')
                self.ui.update()
                canvas = self.view.shop_canvases['sun']
                for card in self.view.shop_cards['sun']:
                    self.assertLessEqual(card.winfo_x() + card.winfo_width(), canvas.winfo_width())
                self.assertGreater(self.view.start_button.winfo_rooty(), self.view.tool_buttons['shortcuts'].winfo_rooty())


if __name__ == '__main__':
    unittest.main()
