"""Public privacy policy + terms pages.

Epic's app registration requires patient-facing apps to publish an https
privacy policy and terms of use. TinyProtocol is a personal, single-family
app, so the honest policy is short: the family's data belongs to the family,
lives in the family's own AWS account, and is never sold or shared.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["legal"])

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — TinyProtocol</title></head>
<body style="font-family: -apple-system, Georgia, serif; background: #FBF7F1; color: #332E40;
max-width: 640px; margin: 0 auto; padding: 40px 20px; line-height: 1.6;">
<h1 style="font-size: 26px">🍼 TinyProtocol — {title}</h1>
<p style="color: #8D8699">Last updated: August 25, 2026</p>
{body}
<hr style="border: none; border-top: 1px solid #EFE7DC; margin: 32px 0">
<p style="color: #8D8699; font-size: 14px">TinyProtocol is a personal feed-and-care tracker
operated by a single family for their own child. It is not a commercial product and is not
medical advice. Contact: tarunkateja.tk@gmail.com</p>
</body></html>"""

_PRIVACY = """
<p>TinyProtocol is a private application used by one family to track their own child's
feeding, growth, and care.</p>
<h3>What we collect</h3>
<p>Feeding logs, diaper and health events, weights, lab results, clinical documents and
related records that the family enters directly or authorizes the app to retrieve from
their accounts (for example, their child's patient portal via the health system's official
patient-access APIs).</p>
<h3>How it is used</h3>
<p>Solely to display the child's information back to the family and their care team.
Health-record access uses OAuth: sign-in happens on the health system's own pages and
TinyProtocol never sees or stores portal passwords — only revocable access tokens.</p>
<h3>What we never do</h3>
<ul>
<li>No selling of data. No advertising. No analytics or tracking of any kind.</li>
<li>No sharing with third parties. Data is stored encrypted at rest in the family's own
private cloud account and is accessible only to authenticated family members.</li>
</ul>
<h3>Your control</h3>
<p>The family can disconnect any linked account at any time from within the app, and can
delete any or all stored data. Portal access can also be revoked from the health system's
own account settings.</p>
"""

_TERMS = """
<p>TinyProtocol is provided as-is for the personal, non-commercial use of the operating
family.</p>
<ul>
<li>It is a record-keeping convenience, <strong>not medical advice</strong>; always follow
the guidance of the child's medical team.</li>
<li>Access is limited to invited family members; each member is responsible for keeping
their sign-in credentials private.</li>
<li>Connected accounts (such as a patient portal) are accessed only with the account
holder's explicit authorization, which may be revoked at any time.</li>
<li>No warranty of any kind is made regarding availability or fitness for a particular
purpose.</li>
</ul>
"""


# Epic's link validator probes with HEAD — answer both methods.
@router.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
def privacy():
    return HTMLResponse(_PAGE.format(title="Privacy Policy", body=_PRIVACY))


@router.api_route("/terms", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
def terms():
    return HTMLResponse(_PAGE.format(title="Terms of Use", body=_TERMS))
