"""PDF attestation generation + opt-in sigstore signing.

Default behavior: generate an unsigned PDF preview alongside the score run.
Opt-in signing (``teammate score --sign``): mint a sigstore keyless signature
via GitHub OIDC, write ``.sig`` and ``.crt`` next to the PDF, and let
``sigstore verify-blob`` round-trip locally.

Why split signing from generation: signing requires an interactive OIDC
browser flow on most laptops. Putting it on the default code path would
break the "no API keys at install" promise. The pre-signed example shipped
in ``examples/attestation.pdf`` is signed once by GitHub Actions OIDC in CI
and committed. That gives every cloner a verifiable artifact without ever
running an OIDC flow themselves.
"""

from __future__ import annotations

import io
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

from teammate import __version__
from teammate.vault import ProbeOutcome, ScoreSummary

# ---------- PDF rendering ----------


def render_pdf(
    summary: ScoreSummary,
    outcomes: list[ProbeOutcome],
) -> bytes:
    """Render a one-page attestation PDF.

    Layout:

      - Page header: "teammate compliance attestation"
      - Score block: overall %, counts breakdown, target path, commit SHA
      - Probe table: probe id, result, framework:control, severity
      - Footer: timestamp, teammate version, signing-status placeholder
        (the actual signing happens later if --sign was passed; the PDF
        itself doesn't claim to be signed).

    Returns raw PDF bytes. Caller decides where to write them.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=4,
    )
    style_body = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontSize=10,
        leading=13,
    )
    style_small = ParagraphStyle(
        "small",
        parent=styles["BodyText"],
        fontSize=8,
        textColor=colors.grey,
    )

    story: list[Any] = []
    story.append(Paragraph("teammate · compliance attestation", style_title))
    story.append(Paragraph(
        "Frameworks: ISO/IEC 27001:2022 Annex A · K-ISMS-P 2.x", style_small
    ))
    story.append(Spacer(1, 10))

    # Score block
    overall_str = (
        f"<b>{summary.overall_pct * 100:.1f}%</b>"
        if summary.overall_pct is not None
        else "<b>n/a</b>"
    )
    counts = summary.counts
    score_block = textwrap.dedent(
        f"""
        <b>Overall:</b> {overall_str}
        &nbsp;&nbsp;<b>Counts:</b>
        pass={counts.get('pass', 0)} ·
        partial={counts.get('partial', 0)} ·
        fail={counts.get('fail', 0)} ·
        n/a={counts.get('n_a', 0)} ·
        indeterminate={counts.get('indeterminate', 0)}
        <br/>
        <b>Target:</b> <font face="Courier">{summary.target_path}</font>
        <br/>
        <b>Commit:</b> <font face="Courier">{summary.commit or '(no git)'}</font>
        <br/>
        <b>Captured:</b> {summary.timestamp}
        """
    ).strip()
    story.append(Paragraph(score_block, style_body))
    story.append(Spacer(1, 14))

    # Probe table
    rows: list[list[Any]] = [["Probe", "Result", "Framework:Control", "Severity"]]
    for o in outcomes:
        ref = (
            f"{o.framework}:{o.control_id}"
            if o.framework and o.control_id
            else "—"
        )
        rows.append([o.probe_id, o.result, ref, o.severity])

    table = Table(rows, colWidths=[1.7 * inch, 0.9 * inch, 2.3 * inch, 0.9 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6f6")]),
                ("FONTNAME", (0, 1), (0, -1), "Courier"),
                ("FONTNAME", (2, 1), (2, -1), "Courier"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))

    # Footer
    footer = (
        f"<i>Generated by teammate v{__version__} · "
        f"signed via sigstore keyless if a `.sig` accompanies this file · "
        f"verify with: sigstore verify-blob this.pdf "
        f"--signature this.pdf.sig --certificate this.pdf.crt</i>"
    )
    story.append(Paragraph(footer, style_small))

    doc.build(story)
    return buffer.getvalue()


# ---------- sigstore signing ----------


class SigstoreUnavailable(RuntimeError):
    """sigstore extras not installed (pip install 'claude-teammate[sign]')."""


def sign_blob(
    pdf_bytes: bytes,
) -> tuple[bytes, bytes]:
    """Sign ``pdf_bytes`` with sigstore keyless. Returns (signature, certificate).

    Raises ``SigstoreUnavailable`` if the optional ``[sign]`` extra wasn't
    installed. Raises ``RuntimeError`` for actual signing failures (auth
    cancelled, network error). Caller decides whether to retry / fall back.
    """
    try:
        from sigstore.oidc import IdentityToken, Issuer
        from sigstore.sign import SigningContext
    except ImportError as exc:
        raise SigstoreUnavailable(
            "sigstore not installed. Re-install with: pip install 'claude-teammate[sign]'"
        ) from exc

    # Use the production sigstore staging-or-prod default. SigningContext
    # picks Fulcio CA + Rekor transparency log automatically.
    issuer = Issuer.production()
    identity = IdentityToken.from_oauth(issuer)  # opens browser; user authenticates
    ctx = SigningContext.production()
    with ctx.signer(identity) as signer:
        bundle = signer.sign_artifact(pdf_bytes)

    # We split the bundle into the (signature, certificate) pair so the
    # README-documented `sigstore verify-blob --signature ... --certificate ...`
    # roundtrip works even for users who don't have the bundle format.
    sig = bundle.signing_certificate.signature  # type: ignore[attr-defined]
    cert = bundle.signing_certificate.public_bytes()  # type: ignore[attr-defined]
    return bytes(sig), bytes(cert)


# ---------- orchestrator: generate (and optionally sign) ----------


def attest(
    summary: ScoreSummary,
    outcomes: list[ProbeOutcome],
    *,
    sign: bool = False,
) -> tuple[bytes, bytes | None, bytes | None]:
    """Build a PDF attestation. Optionally sign. Returns (pdf, sig, crt).

    If signing fails (user cancels OAuth, network error), the PDF is still
    returned with sig=None and crt=None. Caller should report the signing
    failure separately — the unsigned PDF is still useful as a preview.
    """
    pdf = render_pdf(summary, outcomes)
    if not sign:
        return pdf, None, None
    try:
        sig, crt = sign_blob(pdf)
    except SigstoreUnavailable:
        # Surface to caller — they decide whether to print install hint.
        raise
    except Exception:
        # Network/auth failures don't kill the run; PDF without signature
        # is still useful. The caller logs the failure.
        return pdf, None, None
    return pdf, sig, crt


__all__ = [
    "SigstoreUnavailable",
    "attest",
    "render_pdf",
    "sign_blob",
]
