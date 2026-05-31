import _test_path  # noqa: F401

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from deactivate_products_by_date import (
    AccountSession,
    ProductCandidate,
    build_arg_parser,
    configure_account_environment,
    deactivate_candidates,
    fetch_active_products,
    find_all_accounts_dirs,
    list_account_sessions,
    parse_cli_date,
    process_current_account,
    product_sale_label_date,
    select_products_for_deactivation,
)


class DeactivateProductsByDateTests(unittest.TestCase):
    def _create_account(
        self,
        accounts_dir: Path,
        folder_name: str,
        account_id: str,
        name: str,
    ) -> Path:
        state_dir = accounts_dir / folder_name
        state_dir.mkdir(parents=True)
        (state_dir / "account.json").write_text(
            json.dumps({"id": account_id, "name": name}),
            encoding="utf-8",
        )
        (state_dir / "auth.json").write_text(
            json.dumps(
                {
                    "cookies": [
                        {
                            "name": "csrftoken",
                            "value": "token",
                            "domain": ".shafa.ua",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return state_dir

    def test_parse_cli_date_requires_iso_date(self) -> None:
        self.assertEqual(parse_cli_date("2026-05-29"), date(2026, 5, 29))
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            parse_cli_date("29.05.2026")

    def test_product_sale_label_date_reads_nested_date_field(self) -> None:
        self.assertEqual(
            product_sale_label_date({"saleLabel": {"date": "2026-05-29"}}),
            date(2026, 5, 29),
        )
        self.assertIsNone(product_sale_label_date({"saleLabel": {"date": "bad"}}))
        self.assertIsNone(product_sale_label_date({"saleLabel": None}))

    def test_select_products_for_deactivation_filters_inclusive_range(self) -> None:
        products = [
            {
                "id": 101,
                "name": "In range",
                "price": 750,
                "url": "/uk/product/101",
                "saleLabel": {"date": "2026-05-29"},
            },
            {
                "id": 102,
                "name": "After range",
                "saleLabel": {"date": "2026-05-30"},
            },
            {
                "id": 103,
                "name": "No date",
                "saleLabel": {"date": None},
            },
        ]

        candidates = select_products_for_deactivation(
            products,
            start_date=date(2026, 5, 29),
            end_date=date(2026, 5, 29),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].product_id, "101")
        self.assertEqual(candidates[0].name, "In range")
        self.assertEqual(candidates[0].product_date, date(2026, 5, 29))

    def test_fetch_active_products_paginates_and_deduplicates(self) -> None:
        pages = [
            {
                "edges": [{"node": {"id": 101, "name": "First"}}],
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
            },
            {
                "edges": [
                    {"node": {"id": 101, "name": "Duplicate"}},
                    {"node": {"id": 102, "name": "Second"}},
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "cursor-2"},
            },
        ]
        calls = []

        def _fake_feed(**kwargs):
            calls.append(kwargs)
            return pages.pop(0)

        products = fetch_active_products(page_size=50, feed_func=_fake_feed)

        self.assertEqual([item["id"] for item in products], [101, 102])
        self.assertEqual(calls[0]["after"], None)
        self.assertEqual(calls[1]["after"], "cursor-1")
        self.assertEqual(calls[0]["products_type"], "ACTIVE")

    def test_deactivate_candidates_tracks_success_and_failure(self) -> None:
        candidates = [
            ProductCandidate("101", "First", date(2026, 5, 29)),
            ProductCandidate("102", "Second", date(2026, 5, 29)),
        ]
        deactivated = []
        marked = []

        def _fake_deactivate(product_id: str) -> None:
            if product_id == "102":
                raise RuntimeError("failed")
            deactivated.append(product_id)

        def _fake_mark(product_id: str, *, status_title: str) -> bool:
            marked.append((product_id, status_title))
            return True

        with redirect_stdout(StringIO()):
            result = deactivate_candidates(
                candidates,
                deactivate_func=_fake_deactivate,
                mark_inactive_func=_fake_mark,
                sleep_min_seconds=0,
                sleep_max_seconds=0,
            )

        self.assertEqual(result, {"deactivated": 1, "failed": 1, "mark_failed": 0})
        self.assertEqual(deactivated, ["101"])
        self.assertEqual(marked, [("101", "Деактивовано")])

    def test_deactivate_candidates_uses_random_sleep_and_callback(self) -> None:
        candidates = [
            ProductCandidate("101", "First", date(2026, 5, 29)),
            ProductCandidate("102", "Second", date(2026, 5, 29)),
        ]
        processed = []

        def _fake_deactivate(product_id: str) -> None:
            if product_id == "102":
                raise RuntimeError("failed")

        def _on_processed(candidate: ProductCandidate, success: bool) -> None:
            processed.append((candidate.product_id, success))

        with (
            patch("deactivate_products_by_date.random.uniform", return_value=1.5) as uniform,
            patch("deactivate_products_by_date.time.sleep") as sleep,
            redirect_stdout(StringIO()),
        ):
            result = deactivate_candidates(
                candidates,
                deactivate_func=_fake_deactivate,
                mark_inactive_func=lambda *args, **kwargs: True,
                sleep_min_seconds=1.0,
                sleep_max_seconds=2.0,
                on_candidate_processed=_on_processed,
            )

        self.assertEqual(result, {"deactivated": 1, "failed": 1, "mark_failed": 0})
        self.assertEqual(processed, [("101", True), ("102", False)])
        uniform.assert_called_once_with(1.0, 2.0)
        sleep.assert_called_once_with(1.5)

    def test_configure_account_environment_selects_single_saved_session(self) -> None:
        session = AccountSession(
            account_id="acc-1",
            name="Account 1",
            state_dir=Path("/tmp/accounts/acc-1"),
            auth_path=Path("/tmp/accounts/acc-1/auth.json"),
            db_path=Path("/tmp/accounts/acc-1/shafa.sqlite3"),
            media_dir=Path("/tmp/accounts/acc-1/media"),
        )

        with (
            patch(
                "deactivate_products_by_date.list_account_sessions",
                return_value=[session],
            ),
            patch(
                "deactivate_products_by_date.project_root",
                return_value=Path("/tmp/project"),
            ),
            patch.dict(os.environ, {}, clear=True),
        ):
            selected = configure_account_environment()

            self.assertEqual(selected, session)
            self.assertEqual(os.environ["SHAFA_ACCOUNT_ID"], "acc-1")
            self.assertEqual(
                os.environ["SHAFA_STORAGE_STATE_PATH"],
                "/tmp/accounts/acc-1/auth.json",
            )
            self.assertEqual(
                os.environ["SHAFA_DB_PATH"],
                "/tmp/accounts/acc-1/shafa.sqlite3",
            )

    def test_all_accounts_argument_exists(self) -> None:
        args = build_arg_parser().parse_args(["--all-accounts"])

        self.assertTrue(args.all_accounts)

    def test_sleep_range_arguments_exist(self) -> None:
        args = build_arg_parser().parse_args(["--sleep-min", "3.5", "--sleep-max", "9"])

        self.assertEqual(args.sleep_min, 3.5)
        self.assertEqual(args.sleep_max, 9.0)

    def test_parallel_accounts_arguments_exist(self) -> None:
        args = build_arg_parser().parse_args(
            ["--all-accounts", "--parallel-accounts", "--max-workers", "4"]
        )

        self.assertTrue(args.parallel_accounts)
        self.assertEqual(args.max_workers, 4)

    def test_accounts_dir_can_be_passed_multiple_times(self) -> None:
        args = build_arg_parser().parse_args(
            ["--accounts-dir", "/tmp/one/accounts", "--accounts-dir", "/tmp/two/accounts"]
        )

        self.assertEqual(
            args.accounts_dir,
            ["/tmp/one/accounts", "/tmp/two/accounts"],
        )

    def test_accounts_search_root_can_be_passed_multiple_times(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--accounts-search-root",
                "/tmp/root-one",
                "--accounts-search-root",
                "/tmp/root-two",
            ]
        )

        self.assertEqual(
            args.accounts_search_root,
            ["/tmp/root-one", "/tmp/root-two"],
        )

    def test_search_root_loads_sessions_from_multiple_accounts_folders(self) -> None:
        with tempfile.TemporaryDirectory() as raw_base:
            base = Path(raw_base)
            first_accounts = base / "store-one" / "accounts"
            second_accounts = base / "nested" / "store-two" / "accounts"
            self._create_account(first_accounts, "acc-one", "acc-1", "Account 1")
            self._create_account(second_accounts, "acc-two", "acc-2", "Account 2")

            with redirect_stdout(StringIO()):
                sessions = list_account_sessions(accounts_search_roots=[base])

        self.assertEqual(
            [(session.account_id, session.name) for session in sessions],
            [("acc-2", "Account 2"), ("acc-1", "Account 1")],
        )
        self.assertEqual(
            {session.accounts_dir for session in sessions},
            {first_accounts.resolve(), second_accounts.resolve()},
        )

    def test_duplicate_accounts_folders_are_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as raw_base:
            base = Path(raw_base)
            accounts_dir = base / "accounts"
            self._create_account(accounts_dir, "acc-one", "acc-1", "Account 1")

            found = find_all_accounts_dirs(
                accounts_dirs=[accounts_dir, accounts_dir.resolve()],
                accounts_search_roots=[base],
            )

        self.assertEqual(found, [accounts_dir.resolve()])

    def test_configure_account_environment_passes_accounts_discovery_options(self) -> None:
        session = AccountSession(
            account_id="acc-1",
            name="Account 1",
            state_dir=Path("/tmp/accounts/acc-1"),
            auth_path=Path("/tmp/accounts/acc-1/auth.json"),
            db_path=Path("/tmp/accounts/acc-1/shafa.sqlite3"),
            media_dir=Path("/tmp/accounts/acc-1/media"),
        )

        with (
            patch(
                "deactivate_products_by_date.list_account_sessions",
                return_value=[session],
            ) as list_sessions,
            patch(
                "deactivate_products_by_date.project_root",
                return_value=Path("/tmp/project"),
            ),
            patch.dict(os.environ, {}, clear=True),
        ):
            selected = configure_account_environment(
                accounts_dirs=["/tmp/one/accounts"],
                accounts_search_roots=["/tmp/root"],
            )

        self.assertEqual(selected, session)
        list_sessions.assert_called_once_with(
            accounts_dirs=["/tmp/one/accounts"],
            accounts_search_roots=["/tmp/root"],
        )

    def test_process_current_account_uses_provided_candidates(self) -> None:
        candidates = [ProductCandidate("101", "First", date(2026, 5, 29))]
        with (
            patch("deactivate_products_by_date.fetch_active_products") as fetch_products,
            redirect_stdout(StringIO()),
        ):
            result = process_current_account(
                start_date=date(2026, 5, 29),
                end_date=date(2026, 5, 29),
                page_size=50,
                sleep_min_seconds=0,
                sleep_max_seconds=0,
                dry_run=True,
                yes=True,
                candidates=candidates,
            )

        self.assertEqual(result, {"deactivated": 0, "failed": 0, "mark_failed": 0})
        fetch_products.assert_not_called()


if __name__ == "__main__":
    unittest.main()
