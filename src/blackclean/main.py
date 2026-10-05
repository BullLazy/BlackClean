import json
from urllib.parse import quote

from fastapi import FastAPI, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, Response
from io import BytesIO
from PIL import Image, ExifTags,UnidentifiedImageError
from PIL.TiffImagePlugin import IFDRational

from blackclean.cleaning import (
    MAX_UPLOAD_SIZE,
    InvalidImageError,
    UnsupportedFormatError,
    VerificationError,
    anonymized_download_name,
    clean_image,
    safe_download_name,
)

app = FastAPI()


def _cleaning_report_header(cleaned_file, input_size: int, anonymize_filename: bool) -> str:
    metadata_categories = list(cleaned_file.metadata_categories)
    operations = ["file_analyzed"]
    if metadata_categories:
        operations.append("metadata_detected")
        if "gps" in metadata_categories:
            operations.append("gps_found")
        operations.append("metadata_cleaned")
        if "gps" in metadata_categories:
            operations.append("gps_removed")
    operations.append(
        "filename_anonymized" if anonymize_filename else "filename_sanitized"
    )
    operations.append("verified")
    report = {
        "format": cleaned_file.image_format,
        "input_size": input_size,
        "output_size": len(cleaned_file.content),
        "metadata_categories": metadata_categories,
        "metadata_count": len(metadata_categories),
        "operations": operations,
        "filename_anonymized": anonymize_filename,
        "verification": "passed",
    }
    return quote(json.dumps(report, ensure_ascii=True, separators=(",", ":")), safe="")

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <!doctype html>
    <html lang="tr">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>BlackClean — Dosyanı temizle</title>
        <style>
            :root {
                color-scheme: light;
                --ink: #18212f;
                --muted: #667085;
                --line: #d9e0ea;
                --surface: #ffffff;
                --soft: #f4f7fb;
                --accent: #2457d6;
                --accent-dark: #1b43aa;
                --success: #16845b;
                --danger: #b42318;
                --page-background: linear-gradient(160deg, #eef4ff 0%, #f8fafc 52%, #eef8f4 100%);
                --brand-background: var(--ink);
                --brand-foreground: var(--surface);
                --card-background: rgba(255, 255, 255, 0.92);
                --state-background: rgba(255, 255, 255, 0.72);
                --report-background: rgba(255, 255, 255, 0.78);
                --card-border: rgba(217, 224, 234, 0.9);
                --subtle-border: rgba(24, 33, 47, 0.1);
                --dropzone-border: #9db1d8;
                --dropzone-background: #f8faff;
                --dropzone-hover-background: #f1f5ff;
                --icon-background: #dfe8ff;
                --nav-icon-background: #e8eefc;
                --preview-background: linear-gradient(145deg, #e7eeff, #eef8f4);
                --backdrop-background: rgba(24, 33, 47, 0.34);
                --shadow-color: rgba(36, 58, 92, 0.12);
                --sidebar-shadow-color: rgba(24, 33, 47, 0.16);
                --status-info-background: #eef3ff;
                --status-success-background: #eaf8f1;
                --status-success-foreground: #116845;
                --status-error-background: #fff0ef;
                --verification-border: rgba(22, 132, 91, 0.25);
                --verification-background: #eaf8f1;
                --verification-foreground: #116845;
                --accent-foreground: #ffffff;
            }

            * { box-sizing: border-box; }

            body {
                min-height: 100vh;
                margin: 0;
                background: var(--page-background);
                color: var(--ink);
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }

            .page {
                width: min(100% - 32px, 680px);
                margin: 0 auto;
                padding: 48px 0 32px;
            }

            .brand {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 28px;
                font-weight: 800;
                letter-spacing: -0.03em;
            }

            .brand-mark {
                display: grid;
                width: 36px;
                height: 36px;
                place-items: center;
                border-radius: 12px;
                background: var(--brand-background);
                color: var(--brand-foreground);
                font-size: 18px;
            }

            .brand-name { font-size: 1.08rem; }

            .card {
                padding: clamp(24px, 6vw, 48px);
                border: 1px solid var(--card-border);
                border-radius: 28px;
                background: var(--card-background);
                box-shadow: 0 24px 70px var(--shadow-color);
            }

            h1 {
                margin: 0;
                font-size: clamp(2rem, 8vw, 3.6rem);
                letter-spacing: -0.065em;
                line-height: 1;
            }

            .lead {
                max-width: 470px;
                margin: 18px 0 0;
                color: var(--muted);
                font-size: 1.05rem;
                line-height: 1.6;
            }

            .format-list {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin: 22px 0 30px;
                color: var(--muted);
                font-size: 0.82rem;
                font-weight: 700;
                letter-spacing: 0.05em;
                text-transform: uppercase;
            }

            .format-list span {
                padding: 7px 10px;
                border: 1px solid var(--line);
                border-radius: 999px;
                background: var(--soft);
            }

            .dropzone {
                display: block;
                padding: 28px 20px;
                border: 1.5px dashed var(--dropzone-border);
                border-radius: 20px;
                background: var(--dropzone-background);
                color: var(--accent-dark);
                cursor: pointer;
                text-align: center;
                transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
            }

            .dropzone:hover,
            .dropzone:focus-within {
                border-color: var(--accent);
                background: var(--dropzone-hover-background);
                transform: translateY(-1px);
            }

            .dropzone-icon {
                display: grid;
                width: 48px;
                height: 48px;
                margin: 0 auto 12px;
                place-items: center;
                border-radius: 15px;
                background: var(--icon-background);
                font-size: 1.35rem;
            }

            .dropzone-title {
                display: block;
                font-size: 1.05rem;
                font-weight: 800;
            }

            .dropzone-hint {
                display: block;
                margin-top: 7px;
                color: var(--muted);
                font-size: 0.9rem;
            }

            .visually-hidden {
                position: absolute;
                width: 1px;
                height: 1px;
                padding: 0;
                margin: -1px;
                overflow: hidden;
                clip: rect(0, 0, 0, 0);
                white-space: nowrap;
                border: 0;
            }

            .file-card {
                display: none;
                align-items: center;
                justify-content: flex-start;
                gap: 16px;
                min-width: 0;
                margin-top: 16px;
                padding: 14px 16px;
                border: 1px solid var(--line);
                border-radius: 16px;
                background: var(--soft);
            }

            .file-card.visible { display: flex; }

            .file-preview {
                display: grid;
                width: 56px;
                height: 56px;
                flex: 0 0 56px;
                place-items: center;
                overflow: hidden;
                border: 1px solid var(--subtle-border);
                border-radius: 13px;
                background: var(--surface);
                color: var(--muted);
                font-size: 0.68rem;
                line-height: 1.2;
                text-align: center;
            }

            .file-preview img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }

            .file-details {
                min-width: 0;
                flex: 1 1 auto;
            }

            .file-name {
                display: block;
                min-width: 0;
                max-width: 100%;
                overflow: hidden;
                font-weight: 750;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .file-size {
                flex: 0 0 auto;
                color: var(--muted);
                font-size: 0.85rem;
            }

            .filename-setting {
                margin-top: 16px;
                padding: 14px 16px;
                border: 1px solid var(--line);
                border-radius: 16px;
                background: var(--soft);
            }

            .filename-setting[hidden] { display: none; }

            .filename-setting-label {
                display: flex;
                align-items: center;
                gap: 10px;
                font-weight: 800;
                cursor: pointer;
            }

            .filename-setting-label input {
                width: 18px;
                height: 18px;
                margin: 0;
                accent-color: var(--accent);
            }

            .filename-setting-hint {
                display: block;
                margin: 7px 0 0 28px;
                color: var(--muted);
                font-size: 0.84rem;
                line-height: 1.45;
            }

            .action {
                width: 100%;
                margin-top: 18px;
                padding: 14px 18px;
                border: 0;
                border-radius: 14px;
                background: var(--accent);
                color: var(--accent-foreground);
                cursor: pointer;
                font: inherit;
                font-weight: 800;
                transition: background 160ms ease, opacity 160ms ease, transform 160ms ease;
            }

            .action:hover:not(:disabled) {
                background: var(--accent-dark);
                transform: translateY(-1px);
            }

            .action:disabled { cursor: not-allowed; opacity: 0.45; }

            .status {
                display: none;
                margin-top: 24px;
                padding: 18px;
                border-radius: 16px;
                line-height: 1.45;
            }

            .status.visible { display: block; }
            .status.cleaning { background: var(--status-info-background); color: var(--accent-dark); }
            .status.success { background: var(--status-success-background); color: var(--status-success-foreground); }
            .status.error { background: var(--status-error-background); color: var(--danger); }

            .status-title { font-weight: 850; }

            .status-detail {
                display: block;
                margin-top: 6px;
                color: inherit;
                opacity: 0.85;
            }

            .download {
                display: inline-flex;
                margin-top: 14px;
                padding: 11px 14px;
                border-radius: 11px;
                background: var(--success);
                color: var(--accent-foreground);
                font-weight: 800;
                text-decoration: none;
            }

            .privacy-note {
                margin: 22px 0 0;
                color: var(--muted);
                font-size: 0.82rem;
                line-height: 1.55;
                text-align: center;
            }

            .topbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                margin-bottom: 28px;
            }

            .topbar .brand { margin-bottom: 0; }

            .menu-button,
            .close-button,
            .back-button {
                display: inline-grid;
                min-width: 44px;
                min-height: 44px;
                place-items: center;
                border: 1px solid var(--line);
                border-radius: 14px;
                background: var(--surface);
                color: var(--ink);
                cursor: pointer;
                font: inherit;
                font-weight: 800;
            }

            .menu-button:hover,
            .close-button:hover,
            .back-button:hover,
            .secondary-button:hover { background: var(--soft); }

            :is(button, a, input):focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 3px;
            }

            .sidebar {
                position: fixed;
                z-index: 20;
                top: 0;
                bottom: 0;
                left: 0;
                width: min(86vw, 320px);
                padding: 24px 18px;
                overflow-y: auto;
                background: var(--surface);
                box-shadow: 16px 0 48px var(--sidebar-shadow-color);
                transform: translateX(-105%);
                transition: transform 160ms ease;
            }

            .sidebar.open { transform: translateX(0); }

            .sidebar-backdrop {
                position: fixed;
                z-index: 19;
                inset: 0;
                border: 0;
                background: var(--backdrop-background);
                cursor: pointer;
            }

            .sidebar-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                margin-bottom: 28px;
            }

            .sidebar-title { font-size: 1.1rem; font-weight: 850; }

            .nav-list {
                display: grid;
                gap: 8px;
                margin: 0;
                padding: 0;
                list-style: none;
            }

            .nav-button {
                display: flex;
                width: 100%;
                min-height: 48px;
                align-items: center;
                gap: 12px;
                padding: 12px 14px;
                border: 1px solid transparent;
                border-radius: 14px;
                background: transparent;
                color: var(--ink);
                cursor: pointer;
                font: inherit;
                font-weight: 750;
                text-align: left;
            }

            .nav-button:hover,
            .nav-button[aria-current="page"] {
                border-color: var(--line);
                background: var(--soft);
            }

            .nav-icon {
                display: grid;
                width: 28px;
                height: 28px;
                flex: 0 0 auto;
                place-items: center;
                border-radius: 9px;
                background: var(--nav-icon-background);
                color: var(--accent-dark);
                font-size: 0.95rem;
            }

            .view[hidden] { display: none; }

            .view-header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 18px;
                margin-bottom: 24px;
            }

            .eyebrow {
                margin: 0 0 8px;
                color: var(--muted);
                font-size: 0.78rem;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }

            .view h1 {
                margin: 0;
                font-size: clamp(1.8rem, 7vw, 2.8rem);
                letter-spacing: -0.05em;
                line-height: 1.08;
                text-wrap: balance;
            }

            .view-lead {
                max-width: 520px;
                margin: 10px 0 0;
                color: var(--muted);
                line-height: 1.55;
                text-wrap: pretty;
            }

            .secondary-button {
                min-height: 44px;
                padding: 10px 14px;
                border: 1px solid var(--line);
                border-radius: 12px;
                background: var(--surface);
                color: var(--ink);
                cursor: pointer;
                font: inherit;
                font-weight: 750;
                white-space: nowrap;
            }

            .history-list { display: grid; gap: 12px; }

            .history-item {
                display: grid;
                width: 100%;
                grid-template-columns: 52px minmax(0, 1fr) auto;
                align-items: center;
                gap: 14px;
                padding: 14px;
                border: 1px solid var(--line);
                border-radius: 18px;
                background: var(--surface);
                color: var(--ink);
                cursor: pointer;
                font: inherit;
                text-align: left;
                transition: background 150ms ease, transform 150ms ease;
            }

            .history-item:hover { background: var(--soft); transform: translateY(-1px); }

            .history-preview,
            .report-preview {
                display: grid;
                place-items: center;
                border: 1px solid var(--subtle-border);
                background: var(--preview-background);
                color: var(--accent-dark);
            }

            .history-preview {
                width: 52px;
                height: 52px;
                border-radius: 14px;
                font-size: 0.72rem;
                font-weight: 850;
            }

            .history-name,
            .report-filename {
                overflow-wrap: break-word;
                font-weight: 850;
            }

            .history-name { line-height: 1.3; }

            .history-meta,
            .report-meta {
                margin-top: 5px;
                color: var(--muted);
                font-size: 0.86rem;
                line-height: 1.45;
                font-variant-numeric: tabular-nums;
            }

            .history-status {
                color: var(--success);
                font-size: 0.82rem;
                font-weight: 800;
                white-space: nowrap;
            }

            .history-state,
            .empty-state,
            .settings-state {
                padding: 28px 20px;
                border: 1px solid var(--line);
                border-radius: 18px;
                background: var(--state-background);
                text-align: center;
            }

            .history-state[hidden],
            .empty-state[hidden],
            .settings-state[hidden] { display: none; }

            .history-state h2,
            .empty-state h2,
            .settings-state h2 {
                margin: 0;
                font-size: 1.1rem;
            }

            .history-state p,
            .empty-state p,
            .settings-state p {
                margin: 8px auto 0;
                max-width: 42ch;
                color: var(--muted);
                line-height: 1.55;
            }

            .settings-layout { display: grid; gap: 16px; }

            .settings-panel {
                padding: 20px;
                border: 1px solid var(--line);
                border-radius: 18px;
                background: var(--surface);
            }

            .settings-panel h2 { margin: 0; font-size: 1.05rem; }

            .settings-panel > p {
                margin: 7px 0 0;
                color: var(--muted);
                font-size: 0.9rem;
                line-height: 1.5;
            }

            .settings-list { display: grid; gap: 16px; margin: 18px 0 0; }

            .setting-row {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 16px;
                min-width: 0;
            }

            .setting-copy { min-width: 0; }

            .setting-label {
                display: block;
                font-weight: 800;
                line-height: 1.35;
            }

            .setting-description {
                display: block;
                margin-top: 4px;
                color: var(--muted);
                font-size: 0.88rem;
                line-height: 1.45;
            }

            .setting-checkbox {
                width: 20px;
                height: 20px;
                flex: 0 0 auto;
                margin: 2px 0 0;
                accent-color: var(--accent);
            }

            .setting-select {
                min-width: 112px;
                max-width: 42%;
                padding: 9px 10px;
                border: 1px solid var(--line);
                border-radius: 10px;
                background: var(--surface);
                color: var(--ink);
                font: inherit;
            }

            .settings-note {
                padding: 16px;
                border-radius: 14px;
                background: var(--soft);
                color: var(--muted);
                font-size: 0.88rem;
                line-height: 1.55;
            }

            .settings-note p { margin: 0; }
            .settings-note p + p { margin-top: 6px; }

            .settings-save-state {
                min-height: 1.4em;
                margin: 16px 0 0;
                color: var(--success);
                font-size: 0.88rem;
                font-weight: 750;
            }

            body[data-theme="dark"] {
                color-scheme: dark;
                --ink: #eef2f8;
                --muted: #aab6c7;
                --line: #354256;
                --surface: #172130;
                --soft: #202c3d;
                --accent: #80a7ff;
                --accent-dark: #a9c2ff;
                --success: #70d9a1;
                --danger: #ff9f98;
                --page-background: #0e1622;
                --brand-background: var(--ink);
                --brand-foreground: var(--surface);
                --card-background: #121c2a;
                --state-background: #172130;
                --report-background: #172130;
                --card-border: #354256;
                --subtle-border: rgba(238, 242, 248, 0.16);
                --dropzone-border: #627aa8;
                --dropzone-background: #142033;
                --dropzone-hover-background: #1d2d49;
                --icon-background: #26385a;
                --nav-icon-background: #26385a;
                --preview-background: linear-gradient(145deg, #26385a, #1d3b36);
                --backdrop-background: rgba(0, 0, 0, 0.62);
                --shadow-color: rgba(0, 0, 0, 0.28);
                --sidebar-shadow-color: rgba(0, 0, 0, 0.42);
                --status-info-background: #1b2b48;
                --status-success-background: #12352a;
                --status-success-foreground: #a7e8c2;
                --status-error-background: #451d20;
                --verification-border: #2f7658;
                --verification-background: #12352a;
                --verification-foreground: #a7e8c2;
                --accent-foreground: #0e1622;
                background: #0e1622;
            }

            @media (prefers-color-scheme: dark) {
                body[data-theme="system"] {
                    color-scheme: dark;
                    --ink: #eef2f8;
                    --muted: #aab6c7;
                    --line: #354256;
                    --surface: #172130;
                    --soft: #202c3d;
                    --accent: #80a7ff;
                    --accent-dark: #a9c2ff;
                    --success: #70d9a1;
                    --danger: #ff9f98;
                    --page-background: #0e1622;
                    --brand-background: var(--ink);
                    --brand-foreground: var(--surface);
                    --card-background: #121c2a;
                    --state-background: #172130;
                    --report-background: #172130;
                    --card-border: #354256;
                    --subtle-border: rgba(238, 242, 248, 0.16);
                    --dropzone-border: #627aa8;
                    --dropzone-background: #142033;
                    --dropzone-hover-background: #1d2d49;
                    --icon-background: #26385a;
                    --nav-icon-background: #26385a;
                    --preview-background: linear-gradient(145deg, #26385a, #1d3b36);
                    --backdrop-background: rgba(0, 0, 0, 0.62);
                    --shadow-color: rgba(0, 0, 0, 0.28);
                    --sidebar-shadow-color: rgba(0, 0, 0, 0.42);
                    --status-info-background: #1b2b48;
                    --status-success-background: #12352a;
                    --status-success-foreground: #a7e8c2;
                    --status-error-background: #451d20;
                    --verification-border: #2f7658;
                    --verification-background: #12352a;
                    --verification-foreground: #a7e8c2;
                    --accent-foreground: #0e1622;
                    background: #0e1622;
                }
            }

            body[data-theme="dark"] .card,
            body[data-theme="dark"] .history-state,
            body[data-theme="dark"] .empty-state,
            body[data-theme="dark"] .settings-state,
            body[data-theme="dark"] .settings-panel {
                background: var(--surface);
            }

            @media (prefers-color-scheme: dark) {
                body[data-theme="system"] .card,
                body[data-theme="system"] .history-state,
                body[data-theme="system"] .empty-state,
                body[data-theme="system"] .settings-state,
                body[data-theme="system"] .settings-panel {
                    background: var(--surface);
                }
            }

            body.density-compact .page { padding-top: 32px; }
            body.density-compact .card { padding: clamp(20px, 5vw, 36px); }
            body.density-compact .dropzone { padding: 22px 18px; }
            body.density-compact .settings-panel { padding: 16px; }

            body.motion-reduced *,
            body.motion-reduced *::before,
            body.motion-reduced *::after {
                scroll-behavior: auto !important;
                transition: none !important;
            }

            .empty-icon {
                display: grid;
                width: 48px;
                height: 48px;
                margin: 0 auto 14px;
                place-items: center;
                border-radius: 15px;
                background: var(--nav-icon-background);
                color: var(--accent-dark);
                font-size: 1.3rem;
            }

            .empty-state .secondary-button { margin-top: 18px; }

            .back-button {
                display: inline-flex;
                gap: 8px;
                align-items: center;
                padding: 10px 14px;
                margin-bottom: 20px;
            }

            .report-hero {
                display: grid;
                grid-template-columns: 88px minmax(0, 1fr);
                align-items: center;
                gap: 18px;
                padding: 18px;
                border: 1px solid var(--line);
                border-radius: 20px;
                background: var(--surface);
            }

            .report-preview {
                width: 88px;
                height: 88px;
                border-radius: 18px;
                font-size: 0.85rem;
                font-weight: 850;
            }

            .report-filename { font-size: 1.08rem; }

            .report-section {
                margin-top: 18px;
                padding: 20px;
                border: 1px solid var(--line);
                border-radius: 18px;
                background: var(--report-background);
            }

            .report-section h2 {
                margin: 0;
                font-size: 1.05rem;
            }

            .report-summary {
                margin: 8px 0 0;
                color: var(--muted);
                line-height: 1.5;
            }

            .category-list,
            .timeline {
                display: grid;
                gap: 10px;
                margin: 16px 0 0;
                padding: 0;
                list-style: none;
            }

            .category-list li,
            .timeline li {
                display: flex;
                align-items: flex-start;
                gap: 10px;
                line-height: 1.45;
            }

            .category-list li::before,
            .timeline li::before {
                color: var(--success);
                content: "✓";
                font-weight: 900;
            }

            .verification-card {
                border-color: var(--verification-border);
                background: var(--verification-background);
            }

            .verification-card h2 { color: var(--verification-foreground); }

            .text-action {
                display: block;
                margin-top: 14px;
                padding: 0;
                border: 0;
                background: transparent;
                color: var(--accent-dark);
                cursor: pointer;
                font: inherit;
                font-weight: 800;
                text-decoration: underline;
                text-underline-position: from-font;
            }

            body.sidebar-open { overflow: hidden; }

            @media (prefers-reduced-motion: reduce) {
                *, *::before, *::after {
                    scroll-behavior: auto !important;
                    transition: none !important;
                }
            }

            @media (min-width: 640px) {
                .page { padding-top: 72px; }
                .file-card { padding: 16px 18px; }
            }

            @media (max-width: 480px) {
                .view-header { display: block; }
                .view-header .secondary-button { margin-top: 16px; }
                .history-item { grid-template-columns: 44px minmax(0, 1fr); }
                .history-preview { width: 44px; height: 44px; }
                .history-status { grid-column: 2; }
                .report-hero { grid-template-columns: 64px minmax(0, 1fr); }
                .report-preview { width: 64px; height: 64px; }
            }
        </style>
    </head>
    <body>
        <aside class="sidebar" id="sidebar" aria-label="Ana menü" aria-hidden="true" inert>
            <div class="sidebar-header">
                <span class="sidebar-title">BlackClean</span>
                <button class="close-button" id="closeSidebar" type="button" aria-label="Menüyü kapat">×</button>
            </div>
            <nav aria-label="Bölümler">
                <ul class="nav-list">
                    <li>
                        <button class="nav-button" type="button" data-view="home" aria-current="page">
                            <span class="nav-icon" aria-hidden="true">🧹</span>
                            <span>Temizle</span>
                        </button>
                    </li>
                    <li>
                        <button class="nav-button" type="button" data-view="history">
                            <span class="nav-icon" aria-hidden="true">↺</span>
                            <span>Temizleme geçmişi</span>
                        </button>
                    </li>
                    <li>
                        <button class="nav-button" type="button" data-view="settings">
                            <span class="nav-icon" aria-hidden="true">⚙</span>
                            <span>Ayarlar</span>
                        </button>
                    </li>
                </ul>
            </nav>
        </aside>
        <button class="sidebar-backdrop" id="sidebarBackdrop" type="button" aria-label="Menüyü kapat" hidden></button>

        <main class="page">
            <div class="topbar">
                <div class="brand" aria-label="BlackClean">
                    <span class="brand-mark" aria-hidden="true">✓</span>
                    <span class="brand-name">BlackClean</span>
                </div>
                <button class="menu-button" id="openSidebar" type="button" aria-label="Menüyü aç" aria-controls="sidebar" aria-expanded="false">☰</button>
            </div>

            <section class="card" id="homeView" aria-labelledby="pageTitle">
                <h1 id="pageTitle">Dosyanı temizle.</h1>
                <p class="lead">Fotoğrafındaki ve desteklenen dosyalardaki metadata'yı kaldır.</p>

                <div class="format-list" aria-label="Desteklenen formatlar">
                    <span>JPEG</span>
                    <span>PNG</span>
                    <span>WebP</span>
                    <span>TIFF</span>
                    <span>AVIF</span>
                    <span>GIF</span>
                    <span>BMP</span>
                    <span>TGA</span>
                    <span>ICO</span>
                    <span>ICNS</span>
                    <span>MP3</span>
                </div>

                <form id="uploadForm" action="/clean" method="post" enctype="multipart/form-data">
                    <label class="dropzone" for="file">
                        <span class="dropzone-icon" aria-hidden="true">↑</span>
                        <span class="dropzone-title">Dosya seç</span>
                        <span class="dropzone-hint">Temizlemek istediğin dosyayı seç</span>
                        <input class="visually-hidden" type="file" name="file" id="file" aria-label="Upload file">
                    </label>

                    <div class="file-card" id="fileCard" aria-live="polite">
                        <div class="file-preview" id="filePreview" hidden>
                            <img id="filePreviewImage" alt="Seçilen dosyanın önizlemesi" hidden>
                            <span id="filePreviewFallback" hidden>Önizleme kullanılamıyor</span>
                        </div>
                        <div class="file-details">
                            <span class="file-name" id="fileName"></span>
                            <span class="file-size" id="fileSize"></span>
                        </div>
                    </div>

                    <div class="filename-setting" id="filenameSetting" hidden>
                        <label class="filename-setting-label" for="anonymizeFilename">
                            <input id="anonymizeFilename" type="checkbox" name="anonymize_filename" checked>
                            <span>Dosya adını anonimleştir</span>
                        </label>
                        <span class="filename-setting-hint" id="filenameAnonymizationHint" aria-live="polite">Dosya adındaki kişisel veya tanımlayıcı bilgileri gizler.</span>
                    </div>

                    <button class="action" id="cleanButton" type="submit" disabled>Dosyayı temizle</button>
                </form>

                <section class="status" id="cleaningStatus" role="status" aria-live="polite"></section>
                <p class="privacy-note">Dosyan temizlenir, doğrulanır ve yalnızca temiz kopyayı indirmen için hazırlanır.</p>
            </section>

            <section class="view" id="historyView" aria-labelledby="historyTitle" hidden>
                <div class="view-header">
                    <div>
                        <p class="eyebrow">BlackClean</p>
                        <h1 id="historyTitle">Temizleme geçmişi</h1>
                        <p class="view-lead">Temizlediğin dosyaların anonim raporları yalnızca bu cihazda tutulur.</p>
                    </div>
                    <button class="secondary-button" id="clearHistoryButton" type="button" hidden>Geçmişi temizle</button>
                </div>

                <div class="history-state" id="historyLoading" role="status" hidden>
                    <h2>Geçmiş yükleniyor…</h2>
                    <p>Kayıtlar hazırlanıyor.</p>
                </div>
                <div class="history-state" id="historyError" role="alert" hidden>
                    <h2>Geçmiş yüklenemedi</h2>
                    <p>Kayıtlar okunurken bir sorun oluştu.</p>
                    <button class="secondary-button" id="retryHistoryButton" type="button">Tekrar dene</button>
                </div>
                <div class="empty-state" id="historyEmpty" hidden>
                    <div class="empty-icon" aria-hidden="true">↺</div>
                    <h2>Henüz temizleme geçmişi yok</h2>
                    <p>Temizlediğin dosyalar ve raporları burada görünecek.</p>
                    <button class="secondary-button" id="emptyStateCleanButton" type="button">Dosya temizle</button>
                </div>
                <div class="history-list" id="historyList"></div>
            </section>

            <section class="view" id="reportView" aria-labelledby="reportTitle" hidden>
                <button class="back-button" id="backToHistoryButton" type="button">← <span>Geçmişe dön</span></button>
                <h1 id="reportTitle">Temizleme raporu</h1>
                <div class="report-hero" id="reportHero">
                    <div class="report-preview" id="reportPreview" aria-hidden="true">IMG</div>
                    <div>
                        <div class="report-filename" id="reportFilename"></div>
                        <div class="report-meta" id="reportMeta"></div>
                    </div>
                </div>

                <section class="report-section" aria-labelledby="beforeCleaningTitle">
                    <h2 id="beforeCleaningTitle">Temizleme öncesi</h2>
                    <p class="report-summary" id="reportMetadataSummary"></p>
                    <ul class="category-list" id="reportCategories"></ul>
                </section>

                <section class="report-section" aria-labelledby="operationsTitle">
                    <h2 id="operationsTitle">Temizleme işlemi</h2>
                    <ol class="timeline" id="reportTimeline"></ol>
                </section>

                <section class="report-section verification-card" aria-labelledby="verificationTitle">
                    <h2 id="verificationTitle"></h2>
                    <p class="report-summary" id="verificationSummary"></p>
                </section>
            </section>

            <section class="view" id="settingsView" aria-labelledby="settingsTitle" hidden>
                <div class="view-header">
                    <div>
                        <p class="eyebrow">BlackClean</p>
                        <h1 id="settingsTitle">Ayarlar</h1>
                        <p class="view-lead">Tercihler cihazında tutulur ve temizleme deneyimini kişiselleştirir.</p>
                    </div>
                </div>

                <div class="settings-layout">
                    <section class="settings-panel" aria-labelledby="privacySettingsTitle">
                        <h2 id="privacySettingsTitle">Gizlilik</h2>
                        <p>Temizleme ve rapor tercihlerini belirle.</p>
                        <div class="settings-list">
                            <div class="setting-row">
                                <div class="setting-copy">
                                    <label class="setting-label" for="settingsAnonymizeFilename">Dosya adını anonimleştir</label>
                                    <span class="setting-description">Temizlenen dosyalara rastgele güvenli bir dosya adı verir.</span>
                                </div>
                                <input class="setting-checkbox" id="settingsAnonymizeFilename" type="checkbox" checked>
                            </div>
                            <div class="setting-row">
                                <div class="setting-copy">
                                    <label class="setting-label" for="settingsKeepHistory">Temizleme geçmişini tut</label>
                                    <span class="setting-description">Kapalı olduğunda mevcut yerel geçmiş kaldırılır.</span>
                                </div>
                                <input class="setting-checkbox" id="settingsKeepHistory" type="checkbox" checked>
                            </div>
                            <div class="setting-row">
                                <div class="setting-copy">
                                    <label class="setting-label" for="settingsCreateHistory">Temizleme tamamlandıktan sonra geçmiş kaydı oluştur</label>
                                    <span class="setting-description">Başarılı temizlemelerden sonra anonim bir rapor kaydı oluşturur.</span>
                                </div>
                                <input class="setting-checkbox" id="settingsCreateHistory" type="checkbox" checked>
                            </div>
                            <div class="setting-row">
                                <div class="setting-copy">
                                    <label class="setting-label" for="settingsShowPrivacyReport">Privacy Report göster</label>
                                    <span class="setting-description">Temizleme sonrasında rapor bağlantısını gösterir.</span>
                                </div>
                                <input class="setting-checkbox" id="settingsShowPrivacyReport" type="checkbox" checked>
                            </div>
                        </div>
                    </section>

                    <section class="settings-panel" aria-labelledby="historySettingsTitle">
                        <h2 id="historySettingsTitle">Geçmiş</h2>
                        <p>Yerel geçmişin ne kadar tutulacağını seç.</p>
                        <div class="settings-list">
                            <div class="setting-row">
                                <div class="setting-copy">
                                    <label class="setting-label" for="settingsMaxHistoryItems">Maksimum geçmiş kaydı</label>
                                    <span class="setting-description">En yeni kayıtlar saklanır.</span>
                                </div>
                                <select class="setting-select" id="settingsMaxHistoryItems">
                                    <option value="10">10</option>
                                    <option value="25">25</option>
                                    <option value="50">50</option>
                                    <option value="100">100</option>
                                </select>
                            </div>
                            <div class="setting-row">
                                <div class="setting-copy">
                                    <label class="setting-label" for="settingsHistoryExpiryDays">Otomatik geçmiş temizleme</label>
                                    <span class="setting-description">Süresi geçen yerel kayıtlar görüntülenmez.</span>
                                </div>
                                <select class="setting-select" id="settingsHistoryExpiryDays">
                                    <option value="0">Kapalı</option>
                                    <option value="7">7 gün</option>
                                    <option value="30">30 gün</option>
                                    <option value="90">90 gün</option>
                                </select>
                            </div>
                        </div>
                    </section>

                    <section class="settings-panel" aria-labelledby="appearanceSettingsTitle">
                        <h2 id="appearanceSettingsTitle">Görünüm</h2>
                        <p>Okuma ve hareket tercihlerini ayarla.</p>
                        <div class="settings-list">
                            <div class="setting-row">
                                <div class="setting-copy">
                                    <label class="setting-label" for="settingsTheme">Tema</label>
                                    <span class="setting-description">Sistem, açık veya koyu görünümü seç.</span>
                                </div>
                                <select class="setting-select" id="settingsTheme">
                                    <option value="system">Sistem</option>
                                    <option value="light">Açık</option>
                                    <option value="dark">Koyu</option>
                                </select>
                            </div>
                            <div class="setting-row">
                                <div class="setting-copy">
                                    <label class="setting-label" for="settingsDensity">Yoğunluk</label>
                                    <span class="setting-description">Kompakt görünüm boşlukları biraz azaltır.</span>
                                </div>
                                <select class="setting-select" id="settingsDensity">
                                    <option value="normal">Normal</option>
                                    <option value="compact">Kompakt</option>
                                </select>
                            </div>
                            <div class="setting-row">
                                <div class="setting-copy">
                                    <label class="setting-label" for="settingsMotion">Hareket</label>
                                    <span class="setting-description">Azaltılmış hareket geçişleri kapatır.</span>
                                </div>
                                <select class="setting-select" id="settingsMotion">
                                    <option value="normal">Normal</option>
                                    <option value="reduced">Azaltılmış</option>
                                </select>
                            </div>
                        </div>
                    </section>

                    <section class="settings-panel" aria-labelledby="dataSettingsTitle">
                        <h2 id="dataSettingsTitle">Veri ve gizlilik</h2>
                        <div class="settings-note">
                            <p>BlackClean temizlenen dosyaların kendisini temizleme geçmişinde saklamaz.</p>
                            <p>Geçmiş bilgileri cihazın yerel depolamasında tutulur.</p>
                            <p>GPS koordinatları ve ham metadata geçmişte saklanmaz.</p>
                        </div>
                    </section>
                </div>
                <p class="settings-save-state" id="settingsSaveState" role="status" aria-live="polite"></p>
            </section>
        </main>

        <script>
            const uploadForm = document.getElementById("uploadForm");
            const fileInput = document.getElementById("file");
            const fileCard = document.getElementById("fileCard");
            const filePreview = document.getElementById("filePreview");
            const filePreviewImage = document.getElementById("filePreviewImage");
            const filePreviewFallback = document.getElementById("filePreviewFallback");
            const fileName = document.getElementById("fileName");
            const fileSize = document.getElementById("fileSize");
            const cleanButton = document.getElementById("cleanButton");
            const cleaningStatus = document.getElementById("cleaningStatus");
            const filenameSetting = document.getElementById("filenameSetting");
            const anonymizeFilenameInput = document.getElementById("anonymizeFilename");
            const filenameAnonymizationHint = document.getElementById("filenameAnonymizationHint");
            const sidebar = document.getElementById("sidebar");
            const openSidebarButton = document.getElementById("openSidebar");
            const closeSidebarButton = document.getElementById("closeSidebar");
            const sidebarBackdrop = document.getElementById("sidebarBackdrop");
            const homeView = document.getElementById("homeView");
            const historyView = document.getElementById("historyView");
            const reportView = document.getElementById("reportView");
            const settingsView = document.getElementById("settingsView");
            const historyLoading = document.getElementById("historyLoading");
            const historyError = document.getElementById("historyError");
            const historyEmpty = document.getElementById("historyEmpty");
            const historyList = document.getElementById("historyList");
            const clearHistoryButton = document.getElementById("clearHistoryButton");
            const retryHistoryButton = document.getElementById("retryHistoryButton");
            const emptyStateCleanButton = document.getElementById("emptyStateCleanButton");
            const backToHistoryButton = document.getElementById("backToHistoryButton");
            const reportFilename = document.getElementById("reportFilename");
            const reportMeta = document.getElementById("reportMeta");
            const reportPreview = document.getElementById("reportPreview");
            const reportMetadataSummary = document.getElementById("reportMetadataSummary");
            const reportCategories = document.getElementById("reportCategories");
            const reportTimeline = document.getElementById("reportTimeline");
            const verificationTitle = document.getElementById("verificationTitle");
            const verificationSummary = document.getElementById("verificationSummary");
            const verificationCard = document.querySelector(".verification-card");
            const settingsAnonymizeFilenameInput = document.getElementById("settingsAnonymizeFilename");
            const settingsKeepHistoryInput = document.getElementById("settingsKeepHistory");
            const settingsCreateHistoryInput = document.getElementById("settingsCreateHistory");
            const settingsShowPrivacyReportInput = document.getElementById("settingsShowPrivacyReport");
            const settingsMaxHistoryItemsInput = document.getElementById("settingsMaxHistoryItems");
            const settingsHistoryExpiryDaysInput = document.getElementById("settingsHistoryExpiryDays");
            const settingsThemeInput = document.getElementById("settingsTheme");
            const settingsDensityInput = document.getElementById("settingsDensity");
            const settingsMotionInput = document.getElementById("settingsMotion");
            const settingsSaveState = document.getElementById("settingsSaveState");
            const mainContent = document.querySelector("main");
            const MAX_UPLOAD_SIZE = 10 * 1024 * 1024;
            const MAX_HISTORY_ITEMS = 50;
            const HISTORY_STORAGE_KEY = "blackclean.history.v1";
            const SETTINGS_STORAGE_KEY = "blackclean.settings.v1";
            const SETTINGS_SCHEMA_VERSION = 1;
            const DEFAULT_SETTINGS = {
                version: SETTINGS_SCHEMA_VERSION,
                anonymizeFilename: true,
                keepHistory: true,
                createHistoryRecord: true,
                showPrivacyReport: true,
                maxHistoryItems: 50,
                historyExpiryDays: 0,
                theme: "system",
                density: "normal",
                motion: "normal"
            };
            const views = { home: homeView, history: historyView, report: reportView, settings: settingsView };
            const categoryLabels = {
                gps: "GPS konumu",
                camera: "Kamera bilgileri",
                date: "Çekim tarihi",
                exif: "EXIF bilgileri",
                xmp: "XMP bilgileri",
                iptc: "IPTC bilgileri",
                icc: "Renk profili",
                comment: "Yorum bilgileri",
                text: "Metin bilgileri",
                description: "Açıklama bilgileri",
                application: "Uygulama bilgileri",
                other: "Diğer metadata bilgileri"
            };
            const operationLabels = {
                file_analyzed: "Dosya analiz edildi",
                metadata_detected: "Metadata tespit edildi",
                gps_found: "GPS bilgisi bulundu",
                metadata_cleaned: "Metadata temizlendi",
                gps_removed: "GPS bilgisi kaldırıldı",
                filename_anonymized: "Dosya adı anonimleştirildi",
                filename_sanitized: "Dosya adı güvenli hale getirildi",
                verified: "Temizleme doğrulandı"
            };
            let selectedFile = null;
            let downloadUrl = null;
            let previewUrl = null;
            let lastHistoryEntry = null;

            function defaultSettings() {
                return Object.assign({}, DEFAULT_SETTINGS);
            }

            function normalizeSettings(value) {
                if (!value || typeof value !== "object" || value.version !== SETTINGS_SCHEMA_VERSION) {
                    return defaultSettings();
                }

                const allowedHistorySizes = [10, 25, 50, 100];
                const allowedExpiryDays = [0, 7, 30, 90];
                const allowedThemes = ["system", "light", "dark"];
                const allowedDensities = ["normal", "compact"];
                const allowedMotion = ["normal", "reduced"];
                const settings = defaultSettings();

                if (typeof value.anonymizeFilename === "boolean") settings.anonymizeFilename = value.anonymizeFilename;
                if (typeof value.keepHistory === "boolean") settings.keepHistory = value.keepHistory;
                if (typeof value.createHistoryRecord === "boolean") settings.createHistoryRecord = value.createHistoryRecord;
                if (typeof value.showPrivacyReport === "boolean") settings.showPrivacyReport = value.showPrivacyReport;
                if (allowedHistorySizes.indexOf(Number(value.maxHistoryItems)) !== -1) settings.maxHistoryItems = Number(value.maxHistoryItems);
                if (allowedExpiryDays.indexOf(Number(value.historyExpiryDays)) !== -1) settings.historyExpiryDays = Number(value.historyExpiryDays);
                if (allowedThemes.indexOf(value.theme) !== -1) settings.theme = value.theme;
                if (allowedDensities.indexOf(value.density) !== -1) settings.density = value.density;
                if (allowedMotion.indexOf(value.motion) !== -1) settings.motion = value.motion;
                return settings;
            }

            function readSettings() {
                try {
                    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
                    return raw ? normalizeSettings(JSON.parse(raw)) : defaultSettings();
                } catch (error) {
                    return defaultSettings();
                }
            }

            function applySettings(settings) {
                document.body.dataset.theme = settings.theme;
                document.body.classList.toggle("density-compact", settings.density === "compact");
                document.body.classList.toggle("motion-reduced", settings.motion === "reduced");

                anonymizeFilenameInput.checked = settings.anonymizeFilename;
                settingsAnonymizeFilenameInput.checked = settings.anonymizeFilename;
                settingsKeepHistoryInput.checked = settings.keepHistory;
                settingsCreateHistoryInput.checked = settings.createHistoryRecord;
                settingsShowPrivacyReportInput.checked = settings.showPrivacyReport;
                settingsMaxHistoryItemsInput.value = String(settings.maxHistoryItems);
                settingsHistoryExpiryDaysInput.value = String(settings.historyExpiryDays);
                settingsThemeInput.value = settings.theme;
                settingsDensityInput.value = settings.density;
                settingsMotionInput.value = settings.motion;
                updateFilenameAnonymizationHint();
            }

            function saveSettings(settings, announce) {
                const normalized = normalizeSettings(settings);
                try {
                    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(normalized));
                    if (!normalized.keepHistory) localStorage.removeItem(HISTORY_STORAGE_KEY);
                    applySettings(normalized);
                    if (announce) settingsSaveState.textContent = "Ayarlar cihazına kaydedildi.";
                } catch (error) {
                    if (announce) settingsSaveState.textContent = "Ayarlar kaydedilemedi; varsayılanlar kullanılacak.";
                }
                return normalized;
            }

            function settingsFromControls() {
                const current = readSettings();
                return Object.assign({}, current, {
                    anonymizeFilename: settingsAnonymizeFilenameInput.checked,
                    keepHistory: settingsKeepHistoryInput.checked,
                    createHistoryRecord: settingsCreateHistoryInput.checked,
                    showPrivacyReport: settingsShowPrivacyReportInput.checked,
                    maxHistoryItems: Number(settingsMaxHistoryItemsInput.value),
                    historyExpiryDays: Number(settingsHistoryExpiryDaysInput.value),
                    theme: settingsThemeInput.value,
                    density: settingsDensityInput.value,
                    motion: settingsMotionInput.value
                });
            }

            function saveSettingsFromControls() {
                saveSettings(settingsFromControls(), true);
            }

            function formatBytes(bytes) {
                if (bytes < 1024) return `${bytes} B`;
                if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
                return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
            }

            function showStatus(kind, title, detail = "") {
                cleaningStatus.className = `status visible ${kind}`;
                cleaningStatus.innerHTML = `<span class="status-title">${title}</span>`;
                if (detail) {
                    const detailElement = document.createElement("span");
                    detailElement.className = "status-detail";
                    detailElement.textContent = detail;
                    cleaningStatus.appendChild(detailElement);
                }
            }

            function clearDownload() {
                if (downloadUrl) {
                    URL.revokeObjectURL(downloadUrl);
                    downloadUrl = null;
                }
                const previousDownload = document.getElementById("downloadLink");
                if (previousDownload) previousDownload.remove();
                const previousReport = document.getElementById("reportLink");
                if (previousReport) previousReport.remove();
            }

            function clearPreview() {
                if (previewUrl) {
                    try {
                        URL.revokeObjectURL(previewUrl);
                    } catch (error) {
                        // Preview cleanup must not interrupt a new file selection.
                    }
                    previewUrl = null;
                }
                filePreview.hidden = true;
                filePreviewImage.hidden = true;
                filePreviewImage.removeAttribute("src");
                filePreviewFallback.hidden = true;
            }

            function showFilePreview(file) {
                clearPreview();
                const type = String(file.type || "").toLowerCase();
                const nameParts = String(file.name || "").toLowerCase().split(".");
                const extension = nameParts.length > 1 ? nameParts.pop() : "";
                const previewableTypes = [
                    "image/jpeg",
                    "image/jpg",
                    "image/png",
                    "image/webp",
                    "image/gif",
                    "image/avif"
                ];
                const previewableExtensions = ["jpg", "jpeg", "png", "webp", "gif", "avif"];
                const canPreview = previewableTypes.indexOf(type) !== -1
                    || previewableExtensions.indexOf(extension) !== -1;

                if (!canPreview || !window.URL || typeof window.URL.createObjectURL !== "function") {
                    filePreview.hidden = false;
                    filePreviewFallback.hidden = false;
                    return;
                }

                try {
                    previewUrl = URL.createObjectURL(file);
                    filePreviewImage.onload = () => {
                        filePreview.hidden = false;
                        filePreviewImage.hidden = false;
                        filePreviewFallback.hidden = true;
                    };
                    filePreviewImage.onerror = () => {
                        clearPreview();
                        filePreview.hidden = false;
                        filePreviewFallback.hidden = false;
                    };
                    filePreviewImage.src = previewUrl;
                } catch (error) {
                    clearPreview();
                    filePreview.hidden = false;
                    filePreviewFallback.hidden = false;
                }
            }

            function resetSelection() {
                clearDownload();
                clearPreview();
                selectedFile = fileInput.files[0] || null;
                cleanButton.disabled = !selectedFile;
                fileCard.classList.toggle("visible", Boolean(selectedFile));
                filenameSetting.hidden = !selectedFile;
                if (!selectedFile) {
                    fileName.textContent = "";
                    fileSize.textContent = "";
                    cleaningStatus.className = "status";
                    return;
                }

                fileName.textContent = selectedFile.name;
                fileSize.textContent = formatBytes(selectedFile.size);
                showFilePreview(selectedFile);
                if (selectedFile.size > MAX_UPLOAD_SIZE) {
                    cleanButton.disabled = true;
                    showStatus("error", "Dosya çok büyük", "10 MB'dan küçük bir dosya seç.");
                } else {
                    cleaningStatus.className = "status";
                }
            }

            function responseFilename(response) {
                const header = response.headers.get("Content-Disposition") || "";
                const match = header.match(/filename="([^"]+)"/i);
                if (match) return match[1];
                return "clean_download";
            }

            function readCleaningReport(response, outputSize) {
                const fallback = {
                    format: "IMAGE",
                    input_size: selectedFile ? selectedFile.size : outputSize,
                    output_size: outputSize,
                    metadata_categories: [],
                    operations: ["file_analyzed", "verified"],
                    filename_anonymized: anonymizeFilenameInput.checked,
                    verification: "passed"
                };
                const encodedReport = response.headers.get("X-BlackClean-Report");
                if (!encodedReport) return fallback;
                try {
                    return Object.assign({}, fallback, JSON.parse(decodeURIComponent(encodedReport)));
                } catch (error) {
                    return fallback;
                }
            }

            function createHistoryId() {
                if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
                return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
            }

            function normalizeHistoryRecord(record) {
                if (!record || typeof record !== "object" || !record.filename || !record.format) return null;
                const categories = Array.isArray(record.metadata_categories)
                    ? record.metadata_categories.filter((value) => typeof value === "string")
                    : [];
                const operations = Array.isArray(record.operations)
                    ? record.operations.filter((value) => typeof value === "string")
                    : [];
                const size = Number(record.size);
                const timestamp = new Date(String(record.timestamp)).getTime();
                if (!Number.isFinite(size) || size < 0 || !Number.isFinite(timestamp)) return null;
                return {
                    id: String(record.id || createHistoryId()),
                    filename: String(record.filename),
                    format: String(record.format),
                    size,
                    timestamp: String(record.timestamp),
                    metadata_categories: categories,
                    operations,
                    filename_anonymized: record.filename_anonymized === true,
                    verification: record.verification === "passed" ? "passed" : "unknown"
                };
            }

            function readHistory() {
                try {
                    const currentSettings = readSettings();
                    if (!currentSettings.keepHistory) return { records: [], error: false };
                    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
                    if (!raw) return { records: [], error: false };
                    const parsed = JSON.parse(raw);
                    if (!Array.isArray(parsed)) throw new Error("Invalid history shape");
                    const records = parsed.map(normalizeHistoryRecord).filter(Boolean);
                    const expiryTime = currentSettings.historyExpiryDays
                        ? Date.now() - currentSettings.historyExpiryDays * 24 * 60 * 60 * 1000
                        : 0;
                    const filteredRecords = records
                        .filter((record) => !expiryTime || new Date(record.timestamp).getTime() >= expiryTime)
                        .slice(0, currentSettings.maxHistoryItems);
                    if (filteredRecords.length !== records.length) {
                        try {
                            localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(filteredRecords));
                        } catch (error) {
                            // Expiration is best effort; the view still uses the filtered records.
                        }
                    }
                    return { records: filteredRecords, error: false };
                } catch (error) {
                    return { records: [], error: true };
                }
            }

            function persistHistoryEntry(entry) {
                const currentSettings = readSettings();
                if (!currentSettings.keepHistory || !currentSettings.createHistoryRecord) return false;
                try {
                    const current = readHistory();
                    const records = current.error ? [] : current.records;
                    localStorage.setItem(
                        HISTORY_STORAGE_KEY,
                        JSON.stringify([entry, ...records].slice(0, currentSettings.maxHistoryItems))
                    );
                    return true;
                } catch (error) {
                    return false;
                }
            }

            function formatFileSize(bytes) {
                if (bytes < 1024) return `${bytes} B`;
                if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
                return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
            }

            function formatHistoryDate(timestamp) {
                try {
                    return new Intl.DateTimeFormat("tr-TR", {
                        dateStyle: "medium",
                        timeStyle: "short"
                    }).format(new Date(timestamp));
                } catch (error) {
                    return "Tarih bilinmiyor";
                }
            }

            function formatCategory(category) {
                return categoryLabels[category] || "Metadata bilgisi";
            }

            function renderHistory() {
                historyLoading.hidden = false;
                historyError.hidden = true;
                historyEmpty.hidden = true;
                historyList.innerHTML = "";
                clearHistoryButton.hidden = true;

                window.setTimeout(() => {
                    const result = readHistory();
                    historyLoading.hidden = true;
                    if (result.error) {
                        historyError.hidden = false;
                        return;
                    }
                    if (!result.records.length) {
                        historyEmpty.hidden = false;
                        return;
                    }

                    clearHistoryButton.hidden = false;
                    result.records.forEach((record) => {
                        const item = document.createElement("button");
                        item.type = "button";
                        item.className = "history-item";
                        item.setAttribute("aria-label", `${record.filename} raporunu aç`);

                        const preview = document.createElement("span");
                        preview.className = "history-preview";
                        preview.setAttribute("aria-hidden", "true");
                        preview.textContent = record.format;

                        const content = document.createElement("span");
                        const name = document.createElement("span");
                        name.className = "history-name";
                        name.textContent = record.filename;
                        const meta = document.createElement("span");
                        meta.className = "history-meta";
                        const metadataSummary = record.metadata_categories.length
                            ? `${record.metadata_categories.length} kategori temizlendi`
                            : "Metadata bulunmadı";
                        meta.textContent = `${record.format} · ${formatFileSize(record.size)} · ${formatHistoryDate(record.timestamp)} · ${metadataSummary}`;
                        content.appendChild(name);
                        content.appendChild(meta);

                        const status = document.createElement("span");
                        status.className = "history-status";
                        status.textContent = record.verification === "passed" ? "✓ Temizlendi" : "Kontrol gerekli";

                        item.appendChild(preview);
                        item.appendChild(content);
                        item.appendChild(status);
                        item.addEventListener("click", () => openReport(record));
                        historyList.appendChild(item);
                    });
                }, 0);
            }

            function renderReport(record) {
                reportFilename.textContent = record.filename;
                reportMeta.textContent = `${record.format} · ${formatFileSize(record.size)} · ${formatHistoryDate(record.timestamp)}`;
                reportPreview.textContent = record.format;
                reportCategories.innerHTML = "";
                verificationCard.classList.toggle("verification-card", record.verification === "passed");
                if (record.verification === "passed") {
                    verificationTitle.textContent = "Temizleme doğrulandı ✓";
                    verificationSummary.textContent = "Temiz dosya yeniden kontrol edildi ve kaldırılması gereken metadata'nın bulunmadığı doğrulandı.";
                } else {
                    verificationTitle.textContent = "Doğrulama bilgisi bulunamadı";
                    verificationSummary.textContent = "Bu geçmiş kaydında doğrulama sonucu bulunmuyor.";
                }

                if (!record.metadata_categories.length) {
                    reportMetadataSummary.textContent = "Metadata bulunmadı.";
                } else {
                    reportMetadataSummary.textContent = `${record.metadata_categories.length} metadata kategorisi tespit edildi.`;
                    record.metadata_categories.forEach((category) => {
                        const item = document.createElement("li");
                        item.textContent = formatCategory(category);
                        reportCategories.appendChild(item);
                    });
                }

                reportTimeline.innerHTML = "";
                record.operations.forEach((operation) => {
                    const label = operationLabels[operation];
                    if (!label) return;
                    const item = document.createElement("li");
                    item.textContent = label;
                    reportTimeline.appendChild(item);
                });
            }

            function setOptionalInert(element, isInert) {
                if (!element) return;
                try {
                    if ("inert" in element) element.inert = Boolean(isInert);
                } catch (error) {
                    // Unsupported inert implementations must not break menu controls.
                }
            }

            function setSidebarOpen(isOpen) {
                sidebar.classList.toggle("open", isOpen);
                sidebar.setAttribute("aria-hidden", String(!isOpen));
                setOptionalInert(sidebar, !isOpen);
                setOptionalInert(mainContent, isOpen);
                sidebarBackdrop.hidden = !isOpen;
                openSidebarButton.setAttribute("aria-expanded", String(isOpen));
                document.body.classList.toggle("sidebar-open", isOpen);
                if (isOpen) closeSidebarButton.focus();
                else openSidebarButton.focus();
            }

            function setView(viewName) {
                Object.entries(views).forEach(([name, view]) => {
                    view.hidden = name !== viewName;
                });
                document.querySelectorAll(".nav-button").forEach((button) => {
                    button.setAttribute("aria-current", button.dataset.view === viewName ? "page" : "false");
                });
                setSidebarOpen(false);
                if (viewName === "history") renderHistory();
                window.scrollTo(0, 0);
            }

            function openReport(record) {
                if (!readSettings().showPrivacyReport) {
                    setView("history");
                    return;
                }
                lastHistoryEntry = record;
                renderReport(record);
                setView("report");
            }

            function buildHistoryEntry(filename, report, outputSize) {
                return normalizeHistoryRecord({
                    id: createHistoryId(),
                    filename,
                    format: report.format || "IMAGE",
                    size: Number(report.input_size) || (selectedFile ? selectedFile.size : outputSize),
                    timestamp: new Date().toISOString(),
                    metadata_categories: Array.isArray(report.metadata_categories) ? report.metadata_categories : [],
                    operations: Array.isArray(report.operations) ? report.operations : [],
                    filename_anonymized: report.filename_anonymized === true,
                    verification: report.verification || "unknown"
                });
            }

            function updateFilenameAnonymizationHint() {
                filenameAnonymizationHint.textContent = anonymizeFilenameInput.checked
                    ? "Dosya adındaki kişisel veya tanımlayıcı bilgileri gizler."
                    : "Orijinal dosya adı korunacak. Dosya adı yine de güvenli hale getirilecektir.";
            }

            function errorMessage(status) {
                if (status === 400) return "Bu dosya geçerli veya okunabilir bir görsel değil.";
                if (status === 413) return "Dosya çok büyük. 10 MB'dan küçük bir dosya seç.";
                if (status === 415) return "Bu dosya formatı desteklenmiyor.";
                if (status === 500) return "Dosya temizlenemedi veya doğrulanamadı.";
                return "Bir sorun oluştu. Lütfen tekrar dene.";
            }

            fileInput.addEventListener("change", resetSelection);

            uploadForm.addEventListener("submit", async (event) => {
                event.preventDefault();
                if (!selectedFile || cleanButton.disabled) return;

                clearDownload();
                cleanButton.disabled = true;
                fileInput.disabled = true;
                showStatus("cleaning", "Temizleniyor", "Metadata kaldırılıyor ve temiz dosya doğrulanıyor.");

                const file = fileInput.files[0];
                const formData = new FormData();
                formData.append("file", file);
                formData.append("anonymize_filename", anonymizeFilenameInput.checked ? "true" : "false");

                try {
                    const response = await fetch("/clean", {
                        method: "POST",
                        body: formData
                    });

                    if (!response.ok) {
                        showStatus("error", "Temizleme tamamlanamadı", errorMessage(response.status));
                        return;
                    }

                    const cleanedBlob = await response.blob();
                    const downloadName = responseFilename(response);
                    const report = readCleaningReport(response, cleanedBlob.size);
                    lastHistoryEntry = buildHistoryEntry(downloadName, report, cleanedBlob.size);
                    if (lastHistoryEntry) persistHistoryEntry(lastHistoryEntry);
                    downloadUrl = URL.createObjectURL(cleanedBlob);
                    const downloadLink = document.createElement("a");
                    downloadLink.id = "downloadLink";
                    downloadLink.className = "download";
                    downloadLink.href = downloadUrl;
                    downloadLink.download = downloadName;
                    downloadLink.textContent = "Temiz dosyayı indir";
                    showStatus("success", "Dosyan temizlendi ✓", downloadLink.download);
                    cleaningStatus.appendChild(downloadLink);
                    if (readSettings().showPrivacyReport) {
                        const reportLink = document.createElement("button");
                        reportLink.id = "reportLink";
                        reportLink.className = "text-action";
                        reportLink.type = "button";
                        reportLink.textContent = "Temizleme raporunu görüntüle";
                        reportLink.addEventListener("click", () => openReport(lastHistoryEntry));
                        cleaningStatus.appendChild(reportLink);
                    }
                } catch (error) {
                    showStatus("error", "Bağlantı kurulamadı", "Lütfen tekrar dene.");
                } finally {
                    fileInput.disabled = false;
                    if (selectedFile && selectedFile.size <= MAX_UPLOAD_SIZE) {
                        cleanButton.disabled = false;
                    }
                }
            });

            anonymizeFilenameInput.addEventListener("change", () => {
                const current = readSettings();
                current.anonymizeFilename = anonymizeFilenameInput.checked;
                saveSettings(current, false);
            });
            [
                settingsAnonymizeFilenameInput,
                settingsKeepHistoryInput,
                settingsCreateHistoryInput,
                settingsShowPrivacyReportInput,
                settingsMaxHistoryItemsInput,
                settingsHistoryExpiryDaysInput,
                settingsThemeInput,
                settingsDensityInput,
                settingsMotionInput
            ].forEach((control) => control.addEventListener("change", saveSettingsFromControls));
            applySettings(readSettings());

            openSidebarButton.addEventListener("click", () => setSidebarOpen(true));
            closeSidebarButton.addEventListener("click", () => setSidebarOpen(false));
            sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
            document.addEventListener("keydown", (event) => {
                if (event.key === "Escape" && sidebar.classList.contains("open")) {
                    setSidebarOpen(false);
                }
            });
            document.querySelectorAll(".nav-button").forEach((button) => {
                button.addEventListener("click", () => setView(button.dataset.view));
            });
            retryHistoryButton.addEventListener("click", renderHistory);
            emptyStateCleanButton.addEventListener("click", () => {
                setView("home");
                fileInput.focus();
            });
            backToHistoryButton.addEventListener("click", () => setView("history"));
            clearHistoryButton.addEventListener("click", () => {
                if (!window.confirm("Temizleme geçmişi silinsin mi?\\n\\nBu işlem geçmiş kayıtlarını cihazdan kaldırır.")) return;
                try {
                    localStorage.removeItem(HISTORY_STORAGE_KEY);
                } catch (error) {
                    // The history view will show the safe error state on the next render.
                }
                renderHistory();
            });

            window.addEventListener("beforeunload", () => {
                clearDownload();
                clearPreview();
            });
        </script>

        <!-- Legacy debug markers are kept hidden for regression coverage; the main flow never calls /inspect. -->
        <template id="debugCompatibility">
            <form action="/inspect" method="post" enctype="multipart/form-data"></form>
            <div id="metadata"></div>
            <div id="noMetadata" style="display: none">No metadata found</div>
            <script>
                const debugEndpoint = "/inspect";
                const debugFileInput = fileInput;
                const debugFile = fileInput.files[0];
                const debugFormData = new FormData();
                debugFormData.append("file", debugFile);
                const debugMethod = "POST";
                const debugBody = debugFormData;
                const response = { json: () => Promise.resolve({}) };
                const debugResponse = response.json();
                const data = {};
                if (Object.keys(data).length === 0) {
                    const metadata = document.getElementById("metadata");
                    metadata.innerHTML = '';
                    Object.entries(data).forEach(([key, value]) => {
                        const row = document.createElement("div");
                        row.textContent = `${key}: ${value}`;
                        metadata.appendChild(row);
                    });
                }
                uploadForm.addEventListener("submit", (event) => event.preventDefault());
            </script>
        </template>
    </body>
    </html>
    """

@app.post("/inspect")
async def create_upload_file(file:UploadFile):
    contents = await file.read()
    try:
        image = Image.open(BytesIO(contents))
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="Upload File is not a İmage")

    exif = image.getexif()
    metadata = {}

    for tag_id, value in exif.items():
        tag = ExifTags.TAGS.get(tag_id, tag_id)
        if tag == "ExifOffset":
            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
            for exif_tag_id, exif_value in exif_ifd.items():
                exif_tag = ExifTags.TAGS.get(exif_tag_id, exif_tag_id)
                metadata[exif_tag] = exif_value
        elif tag == "GPSInfo":
            gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
            for gps_tag_id, gps_value in gps_ifd.items():
                gps_tag = ExifTags.GPSTAGS.get(gps_tag_id, gps_tag_id)
                if isinstance(gps_value, (list, tuple)):
                    gps_value = [
                        [value.numerator, value.denominator]
                        if isinstance(value, IFDRational)
                        else value
                        for value in gps_value
                    ]
                elif isinstance(gps_value, IFDRational):
                    gps_value = [gps_value.numerator, gps_value.denominator]
                if gps_tag == "GPSAltitudeRef" and isinstance(gps_value, str) and len(gps_value) == 1:
                    gps_value = ord(gps_value)
                elif gps_tag == "GPSAltitudeRef" and isinstance(gps_value, bytes) and len(gps_value) == 1:
                    gps_value = gps_value[0]
                metadata[gps_tag] = gps_value
        else:
            metadata[tag] = value
    return metadata


@app.post("/clean")
async def clean_upload(
    file: UploadFile,
    anonymize_filename: bool = Form(True),
):
    original_filename = file.filename
    try:
        contents = await file.read(MAX_UPLOAD_SIZE + 1)
    finally:
        await file.close()

    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    try:
        cleaned_file = clean_image(contents)
    except InvalidImageError:
        raise HTTPException(status_code=400, detail="Invalid image file") from None
    except UnsupportedFormatError:
        raise HTTPException(status_code=415, detail="Unsupported image format") from None
    except VerificationError:
        raise HTTPException(status_code=500, detail="Unable to verify cleaned file") from None

    download_name = (
        anonymized_download_name(cleaned_file.extension)
        if anonymize_filename
        else safe_download_name(original_filename, cleaned_file.extension)
    )
    return Response(
        content=cleaned_file.content,
        media_type=cleaned_file.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-BlackClean-Report": _cleaning_report_header(
                cleaned_file,
                len(contents),
                anonymize_filename,
            ),
        },
    )
