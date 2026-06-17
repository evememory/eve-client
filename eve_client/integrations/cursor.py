from __future__ import annotations

from eve_client.integrations.provider import ToolProvider, planned_action
from eve_client.models import DetectedTool, ToolPlan


class CursorProvider(ToolProvider):
    def __init__(self) -> None:
        super().__init__(tool="cursor", auth_mode="api-key")

    def build_plan(
        self,
        detected: DetectedTool,
        mcp_base_url: str,
        *,
        auth_mode=None,
        prompt_scope=None,
        hooks_enabled=None,
        scope_env: dict[str, str] | None = None,
    ) -> ToolPlan:
        selected_auth_mode = auth_mode or self.auth_mode
        return ToolPlan(
            tool=self.tool,
            auth_mode=selected_auth_mode,
            supported_auth_modes=self.supported_auth_modes,
            supported=True,
            reason="Cursor integration via hosted HTTP MCP config",
            actions=[
                planned_action(
                    tool=self.tool,
                    action_type="write_config",
                    path=detected.config_path,
                    summary="Add Eve MCP server entry to Cursor MCP config",
                    scope="global-config",
                    requires_backup=True,
                    requires_confirmation=True,
                    idempotent=True,
                    details={
                        "config_format": "json",
                        "mcp_base_url": mcp_base_url,
                        **({"scope_env": dict(scope_env)} if scope_env else {}),
                    },
                ),
                planned_action(
                    tool=self.tool,
                    action_type="auth_setup",
                    path=None,
                    summary="Store Eve-issued API key for Cursor integration",
                    scope="state",
                    requires_backup=False,
                    requires_confirmation=True,
                    idempotent=True,
                    details={"auth_mode": selected_auth_mode},
                ),
            ],
        )
