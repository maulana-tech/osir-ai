"""Send retired server-rendered page URLs to the Next.js UI (``web/``).

The Django templates for these pages are gone; their URL patterns stay so that
``reverse()`` in emails, notifications and remaining views keeps producing a
working link, which now lands on the console page that replaced them.
"""

from __future__ import annotations

from django.http import HttpResponseRedirect


def console(template: str):
    """A view that redirects to ``template`` formatted with the URL kwargs.

    ``console("/w/{workspace_id}/calendar")`` → ``/w/<uuid>/calendar``.
    Query strings are carried over so deep links (``?date=``, ``?tab=``) survive.
    """

    def view(request, **kwargs):
        target = template.format(**{k: str(v) for k, v in kwargs.items()}) if kwargs else template
        if request.META.get("QUERY_STRING"):
            target = f"{target}{'&' if '?' in target else '?'}{request.META['QUERY_STRING']}"
        return HttpResponseRedirect(target)

    view.__name__ = "console_redirect"
    return view
