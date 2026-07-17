from __future__ import annotations

from typing import Any

from .core import JsonHttpClient, ToolError


WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "有雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴强冰雹",
}


class WeatherTool:
    name = "weather"

    def __init__(self, config: dict[str, Any], http: JsonHttpClient):
        self.config = config
        self.http = http

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation != "read":
            raise ToolError("Weather currently supports read-only forecasts.")
        location = arguments.get("location") or self.config.get("location")
        if not location:
            raise ToolError("Weather location is not configured.")
        geocoding = self.http.request_json(
            "GET",
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "zh", "format": "json"},
        )
        matches = geocoding.get("results", []) if isinstance(geocoding, dict) else []
        if not matches:
            raise ToolError(f"Weather location '{location}' was not found.")
        place = matches[0]
        forecast = self.http.request_json(
            "GET",
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 2,
            },
        )
        current = forecast.get("current", {})
        daily = forecast.get("daily", {})
        code = int(current.get("weather_code", 0))
        result = {
            "location": ", ".join(filter(None, [place.get("name"), place.get("admin1"), place.get("country")])),
            "timezone": forecast.get("timezone") or place.get("timezone"),
            "condition": WEATHER_CODES.get(code, f"天气代码 {code}"),
            "temperature_c": current.get("temperature_2m"),
            "apparent_temperature_c": current.get("apparent_temperature"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "today_high_c": self._first(daily.get("temperature_2m_max")),
            "today_low_c": self._first(daily.get("temperature_2m_min")),
            "precipitation_probability": self._first(daily.get("precipitation_probability_max")),
        }
        result["summary"] = (
            f"{result['location']}：{result['condition']}，当前 {result['temperature_c']}℃，"
            f"最高 {result['today_high_c']}℃，最低 {result['today_low_c']}℃，"
            f"降水概率 {result['precipitation_probability']}%"
        )
        return result

    @staticmethod
    def _first(values: Any) -> Any:
        return values[0] if isinstance(values, list) and values else None


class TodoistTool:
    name = "todo"

    def __init__(self, config: dict[str, Any], http: JsonHttpClient):
        self.config = config
        self.http = http

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation != "read":
            raise ToolError("Todoist currently supports read-only task retrieval.")
        token = self.config.get("token")
        if not token:
            raise ToolError("Todoist token is not configured.")
        limit = min(max(int(arguments.get("limit", 20)), 1), 200)
        payload = self.http.request_json(
            "GET",
            "https://api.todoist.com/api/v1/tasks",
            params={"limit": limit},
            headers={"Authorization": f"Bearer {token}"},
        )
        raw_tasks = payload.get("results", []) if isinstance(payload, dict) else payload
        tasks = []
        for task in (raw_tasks or [])[:limit]:
            due = task.get("due") or {}
            tasks.append({
                "id": str(task.get("id")),
                "content": task.get("content", ""),
                "description": task.get("description", ""),
                "priority": task.get("priority", 1),
                "due": due.get("datetime") or due.get("date"),
                "labels": task.get("labels", []),
            })
        tasks.sort(key=lambda item: (item["due"] is None, item["due"] or "", -int(item["priority"])))
        return {"tasks": tasks, "count": len(tasks)}


class GitHubTool:
    name = "github"

    def __init__(self, config: dict[str, Any], http: JsonHttpClient):
        self.config = config
        self.http = http

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation != "read":
            raise ToolError("GitHub currently supports read-only repository inspection.")
        repo = arguments.get("repo") or self.config.get("repo")
        if not repo or "/" not in repo:
            raise ToolError("GitHub repository must use OWNER/REPO format.")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if self.config.get("token"):
            headers["Authorization"] = f"Bearer {self.config['token']}"
        base = f"https://api.github.com/repos/{repo}"
        repository = self.http.request_json("GET", base, headers=headers)
        limit = min(max(int(arguments.get("limit", 10)), 1), 100)
        raw_issues = self.http.request_json(
            "GET", f"{base}/issues", params={"state": "open", "per_page": limit}, headers=headers
        )
        issues = [
            {
                "number": issue.get("number"),
                "title": issue.get("title", ""),
                "updated_at": issue.get("updated_at"),
                "url": issue.get("html_url"),
            }
            for issue in raw_issues
            if "pull_request" not in issue
        ]
        return {
            "repository": repo,
            "description": repository.get("description"),
            "default_branch": repository.get("default_branch"),
            "stars": repository.get("stargazers_count"),
            "forks": repository.get("forks_count"),
            "open_issue_count": repository.get("open_issues_count"),
            "issues": issues,
        }


class NotionTool:
    name = "notion"

    def __init__(self, config: dict[str, Any], http: JsonHttpClient):
        self.config = config
        self.http = http

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation != "read":
            raise ToolError("Notion currently supports read-only page search.")
        token = self.config.get("token")
        if not token:
            raise ToolError("Notion token is not configured.")
        limit = min(max(int(arguments.get("limit", 10)), 1), 100)
        body: dict[str, Any] = {
            "page_size": limit,
            "filter": {"property": "object", "value": "page"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        }
        if arguments.get("query"):
            body["query"] = arguments["query"]
        payload = self.http.request_json(
            "POST",
            "https://api.notion.com/v1/search",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2026-03-11",
            },
            payload=body,
        )
        pages = []
        for page in payload.get("results", []):
            pages.append({
                "id": page.get("id"),
                "title": self._title(page.get("properties", {})),
                "last_edited_time": page.get("last_edited_time"),
                "url": page.get("url"),
            })
        return {"pages": pages, "count": len(pages), "has_more": payload.get("has_more", False)}

    @staticmethod
    def _title(properties: dict[str, Any]) -> str:
        for prop in properties.values():
            title = prop.get("title") if isinstance(prop, dict) else None
            if isinstance(title, list):
                text = "".join(item.get("plain_text", "") for item in title)
                if text:
                    return text
        return "Untitled"
