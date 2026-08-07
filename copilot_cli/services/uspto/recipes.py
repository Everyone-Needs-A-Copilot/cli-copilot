"""Product recipe registry for USPTO contract discovery."""

from __future__ import annotations

from copilot_cli.services.uspto.models import ProductRecipe

RECIPES: dict[str, ProductRecipe] = {
    "ptab": ProductRecipe(
        product="ptab",
        url="https://developer.uspto.gov/ptab-web/#/search/decisions",
        search_selector="input[type='text']",
        submit_selector="button[type='submit']",
        sample_query="IPR2020-00001",
        confirmed=False,
    ),
    "trademark_search": ProductRecipe(
        product="trademark_search",
        url="https://tmsearch.uspto.gov/search/search-information",
        search_selector="input#search-text",
        submit_selector="button#search-submit",
        sample_query="NIKE",
        confirmed=False,
    ),
    "tmog": ProductRecipe(
        product="tmog",
        url="https://tmog.uspto.gov/#",
        search_selector="input[type='text']",
        submit_selector="button[type='submit']",
        sample_query="clothing",
        confirmed=False,
    ),
    "id_manual": ProductRecipe(
        product="id_manual",
        url="https://idm-tmng.uspto.gov/id-master-list-public.html",
        search_selector="input#search",
        submit_selector="button#searchBtn",
        sample_query="software",
        confirmed=False,
    ),
    "design_search": ProductRecipe(
        product="design_search",
        url="https://www.uspto.gov/trademarks/search/design-search-codes",
        search_selector=None,
        submit_selector=None,
        sample_query="",
        confirmed=False,
    ),
    "assignment_search": ProductRecipe(
        product="assignment_search",
        url="https://assignment.uspto.gov/patent/index.html#/patent/search",
        search_selector="input#query",
        submit_selector="button.search-btn",
        sample_query="Google",
        confirmed=False,
    ),
}
