"""Small, provider-independent recovery contract."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RunItemCheckpoint:
    bot: str
    item_key: str
    run_id: str
    phase: str

    @property
    def safely_resumable(self):
        return self.phase in {'pending', 'preparing'}


def recovery_settings(config):
    # Explicit allowlist: never persist OAuth tokens, passwords or API keys.
    keys = ('email_provider', 'send_mode', 'target_resume', 'require_resume_attachment',
            'daily_cap', 'cycle_cap', 'cooldown_hours',
            'excluded_vendor_domains', 'excluded_email_addresses', 'use_ai_email',
            'allow_ai_email_auto_send')
    return {key: config[key] for key in keys if key in config}
