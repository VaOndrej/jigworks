# Invariants and where they are tested

Node ids are relative to `demo/`. Run the whole gate with
`cd demo && uv run pytest -q -p no:cacheprovider`.

Invariants 1-14 and 18 are `@invariant()` methods of the Hypothesis state machine
`btc-paper-trader/tests/property/test_matching_state_machine.py::TestExchangeMachine::runTest`
(4 user accounts plus the house; rules: open, submit of every type and flag, cancel of own / foreign /
unknown ids, reference tick with +-50% gaps and stale gaps, house requote, reset, close). Each
invariant below names its method on `ExchangeMachine` and the focused tests that pin it down.

## Exchange invariants

| # | Invariant | State-machine method | Focused tests |
|---|---|---|---|
| 1 | Per account, cash, BTC, available and reserved are never negative | `inv_01_balances_never_negative` | `tests/unit/test_matching_market_limit.py::test_a_sell_can_never_exceed_free_btc`, `tests/unit/test_house.py::test_quotes_are_limited_by_house_inventory` |
| 2 | Reserved USD / BTC equal the sum over open orders | `inv_02_reservations_equal_open_orders` | `tests/unit/test_fees.py::test_buy_reservation_covers_any_split_into_partial_maker_or_taker_fills`, `tests/unit/test_matching_market_limit.py::test_partial_fill_releases_its_share_of_the_buy_reservation` |
| 3 | The ledger is conserved | `inv_03_ledger_is_conserved` | `tests/unit/test_matching_market_limit.py::test_open_account_issues_100_usd_once_and_is_idempotent` |
| 4 | Global USD and BTC are conserved (totals are 0 with the treasury) | `inv_04_global_conservation` | `tests/api/test_orders_api.py::test_internal_totals_are_zero_for_both_assets` |
| 5 | The book is never crossed after a command | `inv_05_book_never_crossed` | `tests/unit/test_house.py::test_quotes_are_post_only_and_skip_levels_that_would_cross` |
| 6 | Price-time priority | `inv_06_price_time_priority` | `tests/unit/test_matching_market_limit.py::test_within_a_level_the_earliest_order_fills_first`, `tests/unit/test_book.py::test_iter_makers_yields_best_price_then_time_order` |
| 7 | Trades at the maker's price; limits and the +-5% band respected | `inv_07_trades_at_maker_price_within_limit_and_band` | `tests/unit/test_matching_market_limit.py::test_market_buy_fills_level_by_level_at_the_makers_prices`, `::test_market_order_stops_at_the_5_percent_band_and_cancels_the_rest` |
| 8 | Equal trade quantities, fill sums, status transitions, terminal states final | `inv_08_quantities_and_status_transitions` | `tests/unit/test_matching_market_limit.py::test_a_cancelled_order_cannot_change_again` |
| 9 | Maker / taker fees; the sum of fees equals the fee account | `inv_09_fees_follow_maker_taker_and_sum_to_fee_account` | `tests/unit/test_fees.py::test_fee_is_notional_times_rate_rounded_up_to_1e8`, `tests/unit/test_matching_market_limit.py::test_maker_pays_maker_fee_taker_pays_taker_fee_and_both_go_to_the_fee_account` |
| 10 | Quantization and the $1 minimum | `inv_10_quantization_and_minimum` | `tests/unit/test_money.py` (all), `tests/unit/test_matching_market_limit.py::test_invalid_orders_are_rejected_with_their_reason_and_kept_in_history` |
| 11 | Long only: BTC >= 0, a sell never exceeds the free BTC | `inv_11_long_only` (+ checks inside the `submit` rule) | `tests/unit/test_matching_stops.py::test_triggered_stop_is_clipped_to_the_free_btc` |
| 12 | Reduce-only never increases a position; flat means none remain | `inv_12_reduce_only_never_increases_and_flat_has_none` | `tests/unit/test_matching_stops.py::test_becoming_flat_cancels_all_open_reduce_only_orders_with_flat`, `::test_reduce_only_buy_is_rejected` |
| 13 | PnL identity per account (tolerance 1e-6) | `inv_13_pnl_identity` | `tests/unit/test_pnl.py` (all) |
| 14 | A reset equals a fresh account and touches no other account | `inv_14_reset_checked_in_rule` (+ the `reset` rule) | `tests/unit/test_matching_market_limit.py::test_reset_returns_the_account_to_a_fresh_100_and_touches_no_one_else`, `tests/api/test_orders_api.py::test_reset_returns_a_fresh_account_and_leaves_others_untouched` |
| 15 | Persistence round-trip (temporary SQLite) | - | `tests/property/test_persistence_roundtrip.py::test_restart_restores_the_engine_exactly`, `::test_engine_from_records_of_to_records_is_identity`, `tests/api/test_restart.py` (all) |
| 16 | Candle properties (reference and internal) | - | `tests/property/test_candle_properties.py::test_reference_series_candles_are_well_formed`, `::test_aggregating_1m_equals_building_directly`, `::test_internal_trade_candles_are_well_formed`, `::test_sim_history_candles_are_well_formed` |
| 17 | Determinism: same seed and commands, same trades and state | - | `tests/property/test_determinism.py::test_same_commands_give_identical_trades_events_and_records`, `::test_sim_feed_with_the_same_seed_gives_the_same_ticks` |
| 18 | Account isolation | `inv_18_account_isolation` | `tests/unit/test_matching_market_limit.py::test_cancel_of_another_accounts_order_is_not_found_and_changes_nothing` |

## Async quality rules

| Rule | Test |
|---|---|
| A1 The loop is never blocked | `tests/unit/test_store.py::test_committing_10k_account_rows_never_blocks_the_loop`, `tests/unit/test_async_rules.py::test_loop_lag_stays_under_100ms_with_200_bots_house_and_50_ws_clients` |
| A2 Every route and the WebSocket endpoint is a coroutine function | `tests/unit/test_async_rules.py::test_every_route_and_the_websocket_endpoint_are_coroutine_functions` |
| A3 No blocking calls in `src/` | `tests/unit/test_async_rules.py::test_source_has_no_blocking_calls`, `::test_the_ast_scan_itself_detects_violations` |
| A4 Single writer (gathered submits equal sequential application, no lock) | `tests/unit/test_exchange_async.py::test_concurrent_submits_equal_sequential_application_in_enqueue_order`, `::test_exchange_module_uses_no_asyncio_lock` |
| A5 Group commit (N queued commands, one commit) | `tests/unit/test_exchange_async.py::test_commands_enqueued_before_the_task_runs_are_committed_in_one_transaction` |
| A6 A slow WebSocket client delays nobody | `tests/unit/test_broadcast.py::test_a_client_that_never_reads_does_not_delay_others_or_the_exchange` |
| A7 Clean shutdown commits pending commands and leaves no tasks | `tests/unit/test_exchange_async.py::test_leaving_running_commits_pending_commands_and_leaves_no_tasks` |

## Opt-in suites (not part of the gate)

* `BTC_E2E=1`: `tests/e2e/test_trade_flow.py` (Playwright, 1440 px, 50 bots).
* `BTC_LOAD=1`: `tests/load/test_load.py` (1,000 HTTP + WebSocket clients, global conservation over the API).
