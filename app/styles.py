"""Visual styling for the Streamlit interface."""

APP_CSS = """
<style>
:root {
    --ink: #1c2733;
    --muted: #62707d;
    --line: #d8dee4;
    --surface: #ffffff;
    --canvas: #f5f7f8;
    --accent: #c9503c;
    --accent-deep: #a83d2d;
    --support: #146b68;
}

[data-testid="stAppViewContainer"] {
    background: var(--canvas);
}

[data-testid="stHeader"] {
    background: rgba(245, 247, 248, 0.94);
}

[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid var(--line);
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: var(--muted);
}

.block-container {
    max-width: 1320px;
    padding-top: 2.35rem;
    padding-bottom: 2.5rem;
}

.ir-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--line);
    padding: 0 0 1rem 0;
    margin-bottom: 1.15rem;
}

.ir-brand {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 0.72rem;
    padding: 0.5rem 0 1.25rem 0;
    border-bottom: 1px solid var(--line);
    margin-bottom: 1.25rem;
}

.sidebar-label {
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 700;
    margin-bottom: 0.35rem;
    text-transform: uppercase;
}

.sidebar-spacer {
    height: 42vh;
}

[data-testid="stSidebar"] [role="radiogroup"] label {
    border-radius: 5px;
    padding: 0.55rem 0.6rem;
}

[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background: #f3f5f6;
}

.ir-brand-mark {
    width: 34px;
    height: 34px;
    display: grid;
    place-items: center;
    background: var(--ink);
    color: #ffffff;
    border-radius: 6px;
    font-weight: 750;
    font-size: 0.78rem;
}

.ir-brand-name {
    color: var(--ink);
    font-size: 1.02rem;
    font-weight: 720;
    line-height: 1.15;
}

.ir-brand-context {
    color: var(--muted);
    font-size: 0.78rem;
    margin-top: 0.18rem;
}

.ir-header-status {
    color: var(--support);
    font-size: 0.78rem;
    font-weight: 650;
}

.ir-page-heading {
    margin-bottom: 1rem;
}

.ir-page-heading h1 {
    color: var(--ink);
    font-size: 1.62rem;
    line-height: 1.2;
    letter-spacing: 0;
    margin: 0;
}

.ir-page-heading p {
    color: var(--muted);
    font-size: 0.9rem;
    margin: 0.38rem 0 0 0;
}

.page-kicker {
    color: var(--support);
    font-size: 0.74rem;
    font-weight: 720;
    margin-bottom: 0.35rem;
    text-transform: uppercase;
}

.page-kicker.debug {
    color: var(--accent);
}

.section-heading {
    color: var(--ink);
    font-size: 0.96rem;
    font-weight: 720;
    margin: 0 0 0.2rem 0;
}

.section-caption {
    color: var(--muted);
    font-size: 0.8rem;
    margin: 0 0 0.85rem 0;
}

.file-summary {
    color: var(--support);
    font-size: 0.78rem;
    font-weight: 650;
    margin: 0.35rem 0 0.65rem 0;
}

.receipt-strip {
    background: #ecf7f3;
    border: 1px solid #b9ddd2;
    border-left: 4px solid var(--support);
    border-radius: 6px;
    color: var(--ink);
    margin-bottom: 1rem;
    padding: 0.85rem 1rem;
}

.receipt-strip strong {
    color: #0d5754;
}

.pdf-preview {
    align-items: center;
    background: #f2f4f6;
    border: 1px dashed #aeb8c1;
    border-radius: 6px;
    color: var(--muted);
    display: flex;
    justify-content: center;
    min-height: 220px;
    margin: 0.6rem 0;
    padding: 1rem;
    text-align: center;
}

[data-testid="stImage"],
[data-testid="stImage"] img {
    width: 100% !important;
}

[data-testid="stImage"] img {
    height: auto !important;
    object-fit: contain;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--surface);
    border-color: var(--line) !important;
    border-radius: 7px !important;
}

[data-testid="stFileUploaderDropzone"] {
    background: #fafbfc;
    border-color: #b9c3cc;
    border-radius: 6px;
    min-height: 126px;
}

[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--accent);
}

.stTextInput input,
.stTextArea textarea {
    border-radius: 5px;
}

.stTextArea textarea {
    line-height: 1.55;
}

.stButton button,
[data-testid="stFormSubmitButton"] button {
    border-radius: 5px;
    font-weight: 650;
    min-height: 2.55rem;
}

[data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: var(--accent);
    border-color: var(--accent);
}

[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
    background: var(--accent-deep);
    border-color: var(--accent-deep);
}

@media (max-width: 760px) {
    .block-container {
        padding: 2.15rem 0.8rem 2rem 0.8rem;
    }

    .ir-header-status {
        display: none;
    }

    .ir-page-heading h1 {
        font-size: 1.38rem;
    }

    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
    }

    [data-testid="column"] {
        flex: 1 1 100% !important;
        min-width: 100% !important;
        width: 100% !important;
    }
}
</style>
"""
