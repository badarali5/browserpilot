"""Read-only browser state observation helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable


MAX_ELEMENTS = 200
MAX_TEXT_LENGTH = 20_000
MAX_DOM_LENGTH = 20_000

SENSITIVE_ATTRIBUTES = {
    "token",
    "authorization",
    "cookie",
    "session",
    "password",
    "secret",
}


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit] + "...[truncated]"


def is_sensitive_attribute(name: str) -> bool:
    lowered = name.lower()
    return lowered in SENSITIVE_ATTRIBUTES or "token" in lowered or "password" in lowered


async def get_url(page) -> str:
    url = getattr(page, "url", None)
    if isinstance(url, str):
        return url
    return await page.evaluate("window.location.href")


async def get_title(page) -> str:
    return await page.title()


async def extract_visible_interactive_elements(
    page,
    limit: int = MAX_ELEMENTS,
) -> Dict[str, Any]:
    """Extract buttons, links, inputs, and textarea/select elements without values."""
    limit = max(1, min(limit, MAX_ELEMENTS))
    elements = await page.evaluate(
        """
        ({ limit }) => {
          const all = Array.from(document.querySelectorAll(
            'button, a[href], input, textarea, select, [role="button"], [role="link"]'
          ));
          const result = [];
          for (const el of all) {
            if (result.length >= limit) break;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const visible = style.display !== 'none'
              && style.visibility !== 'hidden'
              && style.opacity !== '0'
              && rect.width > 0
              && rect.height > 0;
            if (!visible) continue;

            let name = el.getAttribute('aria-label')
              || el.getAttribute('title')
              || '';
            if (!name && el.labels && el.labels.length) {
              name = Array.from(el.labels).map(label => label.innerText).join(' ').trim();
            }
            if (!name) {
              name = (el.innerText || el.getAttribute('placeholder') || '').trim();
            }
            name = name.slice(0, 500);

            const attrs = {};
            for (const key of ['id', 'name', 'type', 'href', 'placeholder', 'role',
                               'aria-label', 'aria-describedby', 'disabled', 'readonly',
                               'autocomplete', 'for']) {
              if (el.hasAttribute(key)) {
                const value = el.getAttribute(key);
                if (!['password', 'token', 'authorization', 'cookie', 'session', 'secret']
                  .some(part => key.toLowerCase().includes(part)
                    || (value || '').toLowerCase().includes(part))) {
                  attrs[key] = (value || '').slice(0, 500);
                } else {
                  attrs[key] = '[redacted]';
                }
              }
            }

            const tag = el.tagName.toLowerCase();
            const type = (el.getAttribute('type') || '').toLowerCase();
            let kind = 'other';
            if (tag === 'button' || el.getAttribute('role') === 'button') kind = 'button';
            else if (tag === 'a') kind = 'link';
            else if (tag === 'input') kind = type === 'hidden' ? 'hidden' : 'input';
            else if (tag === 'textarea') kind = 'input';
            else if (tag === 'select') kind = 'input';

            result.push({
              kind,
              tag,
              name,
              selector_hint: el.id ? '#' + el.id : (el.name ? '[name="' + el.name + '"]' : null),
              attributes: attrs,
              text: (el.innerText || '').trim().slice(0, 500),
              visible,
              enabled: !el.disabled,
              role: el.getAttribute('role') || tag
            });
          }
          return result;
        }
        """,
        {"limit": limit},
    )
    return {
        "elements": elements,
        "count": len(elements),
        "limit": limit,
    }


async def capture_page_snapshot(page, element_limit: int = MAX_ELEMENTS) -> Dict[str, Any]:
    """Capture a bounded, structured DOM/page snapshot."""
    interactive = await extract_visible_interactive_elements(page, element_limit)
    title = await get_title(page)
    url = await get_url(page)
    visible_text = await page.locator("body").inner_text(timeout=5000)
    visible_text = _truncate(visible_text, MAX_TEXT_LENGTH)

    try:
        dom = await page.evaluate(
            """
            () => {
              const clone = document.body ? document.body.cloneNode(true) : null;
              if (!clone) return '';
              clone.querySelectorAll('script, style, noscript').forEach(node => node.remove());
              clone.querySelectorAll('[value]').forEach(node => {
                const name = (node.getAttribute('name') || '').toLowerCase();
                const type = (node.getAttribute('type') || '').toLowerCase();
                if (type === 'password' || name.includes('password')
                    || name.includes('token') || name.includes('secret')
                    || name.includes('session') || name.includes('authorization')
                    || name.includes('cookie')) {
                  node.setAttribute('value', '[redacted]');
                }
              });
              clone.querySelectorAll('input[type="password"], input[name*="password" i], input[name*="token" i], input[name*="secret" i]').forEach(node => {
                node.setAttribute('value', '[redacted]');
              });
              for (const el of clone.querySelectorAll('*')) {
                for (const attr of Array.from(el.attributes)) {
                  const name = attr.name.toLowerCase();
                  if (name.includes('token') || name.includes('password')
                      || name.includes('secret') || name.includes('authorization')
                      || name.includes('cookie') || name.includes('session')) {
                    el.setAttribute(attr.name, '[redacted]');
                  }
                }
              }
              return '<body>' + clone.innerHTML.slice(0, 30000) + '</body>';
            }
            """
        )
        dom = _truncate(dom, MAX_DOM_LENGTH)
    except Exception:
        dom = ""

    return {
        "url": url,
        "title": title,
        "visible_text": visible_text,
        "interactive": interactive,
        "dom": dom,
        "limits": {
            "elements": element_limit,
            "visible_text_chars": MAX_TEXT_LENGTH,
            "dom_chars": MAX_DOM_LENGTH,
        },
    }
