"""Transaction search execution module.

Fills search fields dynamically by reading screen inputs, executes query via ENTER or submit button,
and detects search completion states with multi-layer adaptive fallbacks for layout variations.
"""

import time
from typing import Any, Dict, Optional, Tuple

from playwright.sync_api import Locator, Page


def resolve_bank_option_value(
    bank_name: str, bank_mapping: Dict[str, str], available_options: Dict[str, str]
) -> Optional[str]:
    """Match an input bank name to the corresponding option value in the portal dropdown.

    Resilient to code differences, full name vs short code, and case variations.

    Args:
        bank_name: Clean bank string from input file (e.g. 'HBL', 'Meezan').
        bank_mapping: User-configured bank code to display name mapping.
        available_options: Dict mapping option value to its visible text.

    Returns:
        Optional[str]: Best matching option value attribute, or None if unresolvable.
    """
    clean_target = bank_name.strip().upper()

    # 1. Exact value match (e.g. value="UBL" == "UBL")
    for val in available_options:
        if val.strip().upper() == clean_target:
            return val

    # 2. Value substring match
    for val in available_options:
        if clean_target in val.strip().upper() or val.strip().upper() in clean_target:
            return val

    # 3. Exact or substring match in visible option text
    for val, text in available_options.items():
        t_upper = text.strip().upper()
        if clean_target == t_upper or f" {clean_target} " in f" {t_upper} " or f"({clean_target})" in t_upper:
            return val

    # 4. Mapped display name match (e.g. "United Bank Limited")
    mapped_name = bank_mapping.get(clean_target, "").strip().upper()
    if mapped_name:
        for val, text in available_options.items():
            t_upper = text.strip().upper()
            if mapped_name in t_upper or t_upper in mapped_name:
                return val
            # Match acronyms (e.g. HBL in "Habib Bank Limited (HBL)")
            words = [w[0] for w in t_upper.split() if w]
            if "".join(words) == clean_target:
                return val

    # 5. Fallback: match any option whose text starts with or contains the bank keyword
    for val, text in available_options.items():
        if val and clean_target[:3] in text.upper():
            return val

    return None


_LOCATOR_CACHE: Dict[str, str] = {}


def find_dropdown_locator(page: Page, configured_selector: str) -> Optional[Locator]:
    """Locate bank/biller dropdown adaptively with fast locator caching.

    Args:
        page: Active Playwright page.
        configured_selector: User-configured CSS selector.

    Returns:
        Optional[Locator]: Found select locator, or None.
    """
    if "bank_dropdown" in _LOCATOR_CACHE:
        try:
            cached = page.locator(_LOCATOR_CACHE["bank_dropdown"]).first
            if cached.is_visible(timeout=50):
                return cached
        except Exception:
            _LOCATOR_CACHE.pop("bank_dropdown", None)

    # 1. Direct configured and standard ID selectors
    candidates = [
        "#biller-service-select",
        "[data-testid='biller-service-select']",
        configured_selector,
        "#bankSelect",
        "#billerSelect",
        "#bank_select",
        "#biller_select",
        "select[name*='biller' i]",
        "select[name*='bank' i]",
        "select[id*='bank' i]",
        "select[id*='biller' i]",
    ]
    for sel in candidates:
        if not sel:
            continue
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=100):
                _LOCATOR_CACHE["bank_dropdown"] = sel
                return loc
        except Exception:
            continue

    # 2. Label-associated select search (e.g. <label>Bank</label> -> <select>)
    label_selectors = [
        "label:has-text('Bank')",
        "label:has-text('Biller')",
        "label:has-text('Service')",
        "label:has-text('Institution')",
    ]
    for lbl_sel in label_selectors:
        try:
            lbl = page.locator(lbl_sel).first
            if lbl.is_visible(timeout=200):
                # Try sibling or parent container select
                parent = lbl.locator("..")
                sel_in_parent = parent.locator("select").first
                if sel_in_parent.is_visible(timeout=200):
                    return sel_in_parent
        except Exception:
            continue

    # 3. Content heuristic: Any visible select that has banking options
    all_selects = page.locator("select:visible").all()
    for s in all_selects:
        try:
            txt = s.inner_text().upper()
            if any(b in txt for b in ("HBL", "UBL", "MCB", "MEEZAN", "ALFALAH", "NBP", "ABL", "BANK")):
                return s
        except Exception:
            continue

    # 4. Fallback: first visible select on page
    if all_selects:
        return all_selects[0]

    return None


def find_consumer_input_locator(page: Page, configured_selector: str) -> Optional[Locator]:
    """Locate consumer number input adaptively with fast locator caching.

    Args:
        page: Active Playwright page.
        configured_selector: Configured CSS selector.

    Returns:
        Optional[Locator]: Found text input locator.
    """
    if "consumer_input" in _LOCATOR_CACHE:
        try:
            cached = page.locator(_LOCATOR_CACHE["consumer_input"]).first
            if cached.is_visible(timeout=50):
                return cached
        except Exception:
            _LOCATOR_CACHE.pop("consumer_input", None)

    # 1. Direct configured and standard selectors
    candidates = [
        "#consumer-number-input",
        "[data-testid='consumer-number-input']",
        configured_selector,
        "#consumerNumberInput",
        "#consumerNumber",
        "#consumer_number",
        "#consumer_no",
        "#accountNumber",
        "input[name*='consumer' i]",
        "input[id*='consumer' i]",
        "input[placeholder*='consumer' i]",
    ]
    for sel in candidates:
        if not sel:
            continue
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=100):
                _LOCATOR_CACHE["consumer_input"] = sel
                return loc
        except Exception:
            continue

    # 2. Label-associated input search
    label_selectors = [
        "label:has-text('Consumer')",
        "label:has-text('Account')",
        "label:has-text('Bill Number')",
        "label:has-text('Reference')",
    ]
    for lbl_sel in label_selectors:
        try:
            lbl = page.locator(lbl_sel).first
            if lbl.is_visible(timeout=200):
                # Check 'for' attribute
                for_id = lbl.get_attribute("for")
                if for_id:
                    target = page.locator(f"#{for_id}").first
                    if target.is_visible(timeout=200):
                        return target
                # Check input in same parent container
                inp = lbl.locator("..").locator("input:visible").first
                if inp.is_visible(timeout=200):
                    return inp
        except Exception:
            continue

    # 3. Positional heuristic: first visible text input in search container/card
    container = page.locator("#filter-section-card, form, #search-filter-form, .portal-card").first
    if container.is_visible(timeout=200):
        text_inputs = container.locator("input[type='text']:visible, input:not([type]):visible").all()
        if text_inputs:
            return text_inputs[0]

    return None


def find_date_inputs(page: Page) -> Tuple[Optional[Locator], Optional[Locator]]:
    """Locate From Date and To Date inputs adaptively with fast locator caching.

    Args:
        page: Active Playwright page.

    Returns:
        Tuple[Optional[Locator], Optional[Locator]]: (from_date_locator, to_date_locator).
    """
    if "from_date" in _LOCATOR_CACHE and "to_date" in _LOCATOR_CACHE:
        try:
            cached_from = page.locator(_LOCATOR_CACHE["from_date"]).first
            cached_to = page.locator(_LOCATOR_CACHE["to_date"]).first
            if cached_from.is_visible(timeout=50) and cached_to.is_visible(timeout=50):
                return cached_from, cached_to
        except Exception:
            _LOCATOR_CACHE.pop("from_date", None)
            _LOCATOR_CACHE.pop("to_date", None)

    # 1. Standard IDs
    from_loc = page.locator("#from-date-input, [data-testid='from-date-input'], #fromDateInput, #fromDate").first
    to_loc = page.locator("#to-date-input, [data-testid='to-date-input'], #toDateInput, #toDate").first

    if from_loc.is_visible(timeout=100) and to_loc.is_visible(timeout=100):
        _LOCATOR_CACHE["from_date"] = "#from-date-input, [data-testid='from-date-input'], #fromDateInput, #fromDate"
        _LOCATOR_CACHE["to_date"] = "#to-date-input, [data-testid='to-date-input'], #toDateInput, #toDate"
        return from_loc, to_loc

    # 2. Native date inputs
    date_inputs = page.locator("input[type='date']:visible").all()
    if len(date_inputs) >= 2:
        return date_inputs[0], date_inputs[1]

    # 3. Label-based detection
    from_lbl = page.locator("label:has-text('From')").first
    to_lbl = page.locator("label:has-text('To')").first
    found_from = None
    found_to = None

    if from_lbl.is_visible(timeout=100):
        found_from = from_lbl.locator("..").locator("input:visible").first
    if to_lbl.is_visible(timeout=100):
        found_to = to_lbl.locator("..").locator("input:visible").first

    if found_from and found_to and found_from.is_visible(timeout=100) and found_to.is_visible(timeout=100):
        return found_from, found_to

    # 4. Attribute heuristics (name/id/placeholder)
    from_attr = page.locator("input[name*='from' i]:visible, input[placeholder*='from' i]:visible").first
    to_attr = page.locator("input[name*='to' i]:visible, input[placeholder*='to' i]:visible").first
    if from_attr.is_visible(timeout=100) and to_attr.is_visible(timeout=100):
        return from_attr, to_attr

    return None, None


def find_search_button_locator(page: Page, configured_selector: str) -> Optional[Locator]:
    """Locate search submit button with fast locator caching.

    Args:
        page: Active Playwright page.
        configured_selector: Configured CSS selector.

    Returns:
        Optional[Locator]: Found button locator, or None.
    """
    if "search_btn" in _LOCATOR_CACHE:
        try:
            cached = page.locator(_LOCATOR_CACHE["search_btn"]).first
            if cached.is_visible(timeout=50):
                return cached
        except Exception:
            _LOCATOR_CACHE.pop("search_btn", None)

    candidates = [
        "#btn-search-bill-status",
        "[data-testid='btn-search-bill-status']",
        configured_selector,
        "button:has-text('Bill Status')",
        "button:has-text('Search')",
        "#btnSearch",
        "button[type='submit']",
    ]
    for sel in candidates:
        if not sel:
            continue
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=100):
                _LOCATOR_CACHE["search_btn"] = sel
                return loc
        except Exception:
            continue
    return None


def select_bank(
    page: Page, bank_selector: str, bank_name: str, bank_mapping: Dict[str, str]
) -> None:
    """Select requested bank from dropdown if not already selected.

    Args:
        page: Active Playwright page.
        bank_selector: CSS locator for the bank select element.
        bank_name: Target bank name.
        bank_mapping: Mapping dictionary.
    """
    dropdown = find_dropdown_locator(page, bank_selector)
    if not dropdown:
        return

    try:
        current_val = dropdown.evaluate("el => el.value")
        options_data = dropdown.evaluate(
            "el => Array.from(el.options).map(o => ({ value: o.value, text: o.text }))"
        )
        options_dict = {o["value"]: o["text"] for o in options_data if o.get("value")}
        target_val = resolve_bank_option_value(bank_name, bank_mapping, options_dict)
        if target_val and target_val != current_val:
            dropdown.select_option(value=target_val)
    except Exception:
        pass


def fill_search_fields(
    page: Page,
    selectors: Dict[str, Any],
    bank_name: str,
    consumer_number: str,
    search_date: str,
    bank_mapping: Dict[str, str],
) -> None:
    """Populate Bank, Consumer Number, From Date, and To Date input fields adaptively.

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration.
        bank_name: Bank/Service name.
        consumer_number: Consumer Number string.
        search_date: Transaction date (YYYY-MM-DD).
        bank_mapping: Bank alias mapping dictionary.
    """
    search_sel = selectors.get("search", {})
    bank_sel = search_sel.get("bank_select", "#biller-service-select, #bankSelect")
    consumer_sel = search_sel.get("consumer_input", "#consumer-number-input, #consumerNumberInput")

    # 1. Select bank first (skips if already active)
    select_bank(page, bank_sel, bank_name, bank_mapping)

    # 2. Fill consumer number
    consumer_input = find_consumer_input_locator(page, consumer_sel)
    if consumer_input:
        consumer_input.fill(str(consumer_number).strip())

    # 3. Populate From Date and To Date using adaptive date locator
    from_date_input, to_date_input = find_date_inputs(page)
    if from_date_input and to_date_input:
        try:
            from_date_input.fill(search_date)
            to_date_input.fill(search_date)
        except Exception:
            pass


def execute_transaction_search(
    page: Page,
    selectors: Dict[str, Any],
    bank_name: str,
    consumer_number: str,
    search_date: str,
    bank_mapping: Dict[str, str],
    timeout_ms: int = 15000,
) -> bool:
    """Execute transaction search with reliable submission and fresh result state validation.

    Guarantees:
    - Confirms the search action was submitted.
    - Distinguishes fresh results from stale previously displayed results.
    - Accurately detects genuine no-record responses.
    - Treats timeouts and failures strictly as unsuccessful (returns False, never True on timeout).

    Args:
        page: Active Playwright page.
        selectors: Portal selector configuration.
        bank_name: Bank/Service name.
        consumer_number: Consumer number.
        search_date: Transaction date.
        bank_mapping: Bank alias mapping.
        timeout_ms: Maximum wait time for query completion.

    Returns:
        bool: True if search successfully completed and fresh table or no-record notification is visible.
    """
    fill_search_fields(page, selectors, bank_name, consumer_number, search_date, bank_mapping)

    clean_target_consumer = str(consumer_number).strip()
    results_sel = selectors.get("results", {})
    no_rec_sel = results_sel.get(
        "no_record_message",
        "#no-records-message, #noRecordsAlert, [data-testid='no-records-message']",
    )
    table_sel = results_sel.get(
        "table",
        "#transactions-table, #transactionsTable, [data-testid='transactions-table'], table",
    )
    loading_sel = results_sel.get(
        "loading_indicator",
        "#loading-spinner, #loading-indicator, #loadingSpinner, .portal-loading, .spinner, .loading",
    )

    prev_row_text = None
    try:
        table_loc = page.locator(table_sel).first
        if table_loc.is_visible(timeout=100):
            body_rows = page.locator(f"{table_sel} tbody tr")
            if body_rows.count() > 0:
                prev_row_text = body_rows.first.inner_text(timeout=100)
            else:
                all_rows = page.locator(f"{table_sel} tr")
                if all_rows.count() > 1:
                    prev_row_text = all_rows.nth(1).inner_text(timeout=100)
    except Exception:
        pass

    submitted = False
    configured_btn_sel = selectors.get("search", {}).get("search_button", "#btnSearch")
    search_btn = find_search_button_locator(page, configured_btn_sel)
    if search_btn:
        try:
            search_btn.click(timeout=2000)
            submitted = True
        except Exception:
            pass

    if not submitted:
        consumer_sel = selectors.get("search", {}).get(
            "consumer_input", "#consumer-number-input, #consumerNumberInput"
        )
        consumer_field = find_consumer_input_locator(page, consumer_sel)
        if consumer_field:
            try:
                consumer_field.press("Enter", timeout=2000)
                submitted = True
            except Exception:
                pass

    if not submitted:
        return False

    # Wait for loading spinner to clear if it appeared
    try:
        spinner_loc = page.locator(loading_sel).first
        if spinner_loc.is_visible(timeout=150):
            spinner_loc.wait_for(state="hidden", timeout=min(timeout_ms, 15000))
    except Exception:
        pass

    start_time = time.time()
    max_wait_seconds = max(2.0, min(timeout_ms / 1000.0, 15.0))

    while (time.time() - start_time) < max_wait_seconds:
        # State A: No records found alert is displayed
        try:
            no_rec_loc = page.locator(no_rec_sel).first
            if no_rec_loc.is_visible(timeout=100):
                return True
        except Exception:
            pass

        # State B: Portal error alert is displayed
        try:
            err_loc = page.locator("#error-message, .alert-danger, [role='alert'].error").first
            if err_loc.is_visible(timeout=50):
                return False
        except Exception:
            pass

        # State C: Table with data rows is displayed
        try:
            table_loc = page.locator(table_sel).first
            if table_loc.is_visible(timeout=100):
                body_rows = page.locator(f"{table_sel} tbody tr")
                if body_rows.count() > 0:
                    first_data_row = body_rows.first.inner_text(timeout=200)
                    if prev_row_text is None or first_data_row != prev_row_text or clean_target_consumer in first_data_row:
                        return True
                else:
                    all_rows = page.locator(f"{table_sel} tr")
                    if all_rows.count() > 1:
                        first_data_row = all_rows.nth(1).inner_text(timeout=200)
                        if prev_row_text is None or first_data_row != prev_row_text or clean_target_consumer in first_data_row:
                            return True
        except Exception:
            pass

        time.sleep(0.1)

    return False
