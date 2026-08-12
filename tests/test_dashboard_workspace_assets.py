from __future__ import annotations

from pathlib import Path


ASSETS = Path(__file__).parents[1] / "src" / "nexus" / "dashboard"


def test_workspace_html_has_semantic_views_controls_and_csrf_bootstrap() -> None:
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    assert html.count('role="tab"') == 8
    for name in ("habits", "projects", "suggestions"):
        assert f'id="tab-{name}"' in html
        assert f'id="panel-{name}"' in html
        assert f'id="{name}-content"' in html
    assert 'name="nexus-csrf"' in html
    assert "__NEXUS_CSRF_TOKEN__" in html
    assert 'rel="icon" href="data:,"' in html
    assert 'id="replan-dialog"' in html
    assert 'id="confirm-dialog"' in html
    assert "<dialog" in html


def test_workspace_script_uses_safe_dom_and_allowlisted_mutations() -> None:
    script = (ASSETS / "dashboard.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script
    assert "textContent" in script
    assert "X-Nexus-CSRF" in script
    assert "apiPost" in script
    for path in (
        "/api/habits/",
        "/api/projects/",
        "/api/suggestions/",
        "/api/replan/preview",
        "/api/replan/apply",
    ):
        assert path in script
    for renderer in ("renderHabits", "renderProjects", "renderSuggestions"):
        assert renderer in script
    assert "aria-busy" in script
    assert "{ increment: 1 }" in script
    assert "events: []" not in script
    assert 'summary.progress_source === "milestones"' in script
    assert "source_types || []" in script
    assert "context.degradations || []" in script


def test_workspace_css_has_stable_controls_progress_and_mobile_layout() -> None:
    css = (ASSETS / "dashboard.css").read_text(encoding="utf-8")
    assert ".action-button" in css
    assert ".progress-track" in css
    assert ".dialog-shell" in css
    assert "grid-template-columns: repeat(8" in css
    assert "overflow-x: auto" in css
