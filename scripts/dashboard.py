"""
dashboard.py — interactive Streamlit dashboard for exploring your Zotero library.

Run with:
    streamlit run scripts/dashboard.py

Reads from data/cache/items_with_text.json if available, otherwise falls
back to data/cache/items.json. Re-run extract_text.py to get PDF coverage data.
"""

import json
import sys
from pathlib import Path
from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st

# ── Path fix ──────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

PROJECT_ROOT = Path(__file__).parent.parent
ITEMS_WITH_TEXT  = PROJECT_ROOT / "data" / "cache" / "items_with_text.json"
ITEMS_CACHE      = PROJECT_ROOT / "data" / "cache" / "items.json"
ASSIGNMENTS_FILE = PROJECT_ROOT / "data" / "cache" / "tag_assignments.json"


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data
def load_assignments() -> list[dict]:
    """Load the dry-run tag assignments if available."""
    if not ASSIGNMENTS_FILE.exists():
        return []
    with open(ASSIGNMENTS_FILE) as f:
        return json.load(f)


@st.cache_data
def load_items() -> tuple[list[dict], str]:
    """Load items from the best available cache file."""
    if ITEMS_WITH_TEXT.exists():
        path = ITEMS_WITH_TEXT
    elif ITEMS_CACHE.exists():
        path = ITEMS_CACHE
    else:
        return [], "no cache found"
    with open(path) as f:
        return json.load(f), path.name


def to_dataframe(items: list[dict]) -> pd.DataFrame:
    """Flatten items list into a pandas DataFrame for filtering and display."""
    rows = []
    for item in items:
        tags = item.get("tags", [])
        rows.append({
            "key":              item["key"],
            "title":            item.get("title", "(no title)"),
            "item_type":        item.get("item_type", ""),
            "creators":         "; ".join(item.get("creators", [])[:3]),
            "publication_date": item.get("publication_date", ""),
            "date_added":       item.get("date_added", "")[:10],
            "tags":             ", ".join(tags),
            "tag_count":        len(tags),
            "has_pdf_text":     item.get("pdf_text") is not None,
            "pdf_source":       item.get("pdf_text_source") or "none",
            "text_length":      len(item.get("pdf_text") or ""),
        })
    return pd.DataFrame(rows)


# ── App ───────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Zotero Library Dashboard",
    page_icon="📚",
    layout="wide",
)

st.title("📚 Zotero Library Dashboard")

items, source_file = load_items()

if not items:
    st.error("No cache files found. Run `python scripts/fetch_items.py` first.")
    st.stop()

df = to_dataframe(items)

# ── Sidebar filters ───────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")

    # Item type filter
    all_types = sorted(df["item_type"].unique())
    selected_types = st.multiselect(
        "Item type",
        options=all_types,
        default=all_types,
    )

    # PDF coverage filter
    pdf_filter = st.radio(
        "PDF coverage",
        options=["All items", "Has PDF text", "No PDF text"],
        index=0,
    )

    # Tag filter
    tag_search = st.text_input("Filter by tag (partial match)", "")

    # Date added range
    years = sorted(df["date_added"].str[:4].dropna().unique())
    years = [y for y in years if y.isdigit()]
    if years:
        year_range = st.select_slider(
            "Date added (year)",
            options=years,
            value=(years[0], years[-1]),
        )
    else:
        year_range = None

    st.divider()
    st.caption(f"Data source: `{source_file}`")
    if st.button("Clear cache and reload"):
        st.cache_data.clear()
        st.rerun()

# ── Apply filters ─────────────────────────────────────────────────────────────

filtered = df[df["item_type"].isin(selected_types)]

if pdf_filter == "Has PDF text":
    filtered = filtered[filtered["has_pdf_text"]]
elif pdf_filter == "No PDF text":
    filtered = filtered[~filtered["has_pdf_text"]]

if tag_search:
    filtered = filtered[
        filtered["tags"].str.contains(tag_search, case=False, na=False)
    ]

if year_range:
    filtered = filtered[
        filtered["date_added"].str[:4].between(year_range[0], year_range[1])
    ]

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_overview, tab_types, tab_tags, tab_pdfs, tab_assignments, tab_browse = st.tabs([
    "Overview", "Item Types", "Tags", "PDF Coverage", "Tag Assignments", "Browse"
])


# ── Tab 1: Overview ───────────────────────────────────────────────────────────

with tab_overview:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total items", f"{len(filtered):,}")
    with col2:
        tagged = (filtered["tag_count"] > 0).sum()
        st.metric("Tagged", f"{tagged:,}", f"{tagged/len(filtered)*100:.0f}%")
    with col3:
        has_pdf = filtered["has_pdf_text"].sum()
        st.metric("Has PDF text", f"{has_pdf:,}", f"{has_pdf/len(filtered)*100:.0f}%")
    with col4:
        untagged = (filtered["tag_count"] == 0).sum()
        st.metric("Untagged", f"{untagged:,}", f"{untagged/len(filtered)*100:.0f}%")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Items added per year")
        year_counts = (
            filtered["date_added"].str[:4]
            .value_counts()
            .sort_index()
            .reset_index()
        )
        year_counts.columns = ["year", "count"]
        fig = px.bar(year_counts, x="year", y="count", labels={"year": "Year added", "count": "Items"})
        fig.update_layout(margin=dict(t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("Tags per item")
        tag_dist = filtered["tag_count"].value_counts().sort_index().reset_index()
        tag_dist.columns = ["tag_count", "items"]
        fig = px.bar(tag_dist, x="tag_count", y="items",
                     labels={"tag_count": "Number of tags", "items": "Items"})
        fig.update_layout(margin=dict(t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)


# ── Tab 2: Item Types ─────────────────────────────────────────────────────────

with tab_types:
    st.subheader("Items by type")

    type_counts = (
        filtered["item_type"]
        .value_counts()
        .reset_index()
    )
    type_counts.columns = ["item_type", "count"]

    fig = px.bar(
        type_counts,
        x="count",
        y="item_type",
        orientation="h",
        labels={"item_type": "Item type", "count": "Count"},
        height=max(300, len(type_counts) * 30),
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)


# ── Tab 3: Tags ───────────────────────────────────────────────────────────────

with tab_tags:
    st.subheader("Tag frequency")

    # Explode the comma-joined tags back into individual tags for counting
    all_tags: list[str] = []
    for tags_str in filtered["tags"].dropna():
        if tags_str:
            all_tags.extend(t.strip() for t in tags_str.split(",") if t.strip())

    if not all_tags:
        st.info("No tags found in the filtered selection.")
    else:
        tag_counts = Counter(all_tags)
        top_n = st.slider("Show top N tags", min_value=10, max_value=min(100, len(tag_counts)), value=30)

        top_tags = pd.DataFrame(
            tag_counts.most_common(top_n),
            columns=["tag", "count"],
        )

        fig = px.bar(
            top_tags,
            x="count",
            y="tag",
            orientation="h",
            labels={"tag": "Tag", "count": "Items"},
            height=max(400, top_n * 22),
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

        st.caption(f"{len(tag_counts)} unique tags across {len(filtered)} items.")


# ── Tab 4: PDF Coverage ───────────────────────────────────────────────────────

with tab_pdfs:
    st.subheader("PDF coverage")

    # Only meaningful if we have source data (items_with_text.json)
    has_source_data = "pdf_text_source" in df.columns and source_file == "items_with_text.json"

    col1, col2 = st.columns([1, 2])

    with col1:
        source_counts = filtered["pdf_source"].value_counts().reset_index()
        source_counts.columns = ["source", "count"]
        source_counts["source"] = source_counts["source"].replace({
            "local": "Local storage",
            "webdav": "WebDAV mount",
            "none": "No PDF",
        })
        fig = px.pie(
            source_counts,
            values="count",
            names="source",
            color="source",
            color_discrete_map={
                "Local storage": "#4C72B0",
                "WebDAV mount": "#55A868",
                "No PDF": "#C44E52",
            },
        )
        fig.update_layout(margin=dict(t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("PDF coverage by item type")
        pdf_by_type = (
            filtered.groupby("item_type")["has_pdf_text"]
            .agg(["sum", "count"])
            .reset_index()
        )
        pdf_by_type.columns = ["item_type", "with_pdf", "total"]
        pdf_by_type["pct"] = (pdf_by_type["with_pdf"] / pdf_by_type["total"] * 100).round(1)
        pdf_by_type = pdf_by_type.sort_values("total", ascending=False)

        fig = px.bar(
            pdf_by_type,
            x="item_type",
            y="pct",
            labels={"item_type": "Item type", "pct": "% with PDF text"},
            hover_data={"with_pdf": True, "total": True},
        )
        fig.update_layout(margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    if not has_source_data:
        st.info(
            "Source breakdown (local vs. WebDAV) requires running "
            "`python scripts/extract_text.py` first."
        )


# ── Tab 5: Tag Assignments ────────────────────────────────────────────────────

with tab_assignments:
    assignments = load_assignments()

    if not assignments:
        st.info(
            "No tag assignment preview found. "
            "Run `python scripts/assign_tags.py` (dry run) to generate one."
        )
    else:
        # ── Metrics ───────────────────────────────────────────────────────────
        n_assigned  = sum(1 for a in assignments if a.get("proposed_tags"))
        n_none      = sum(1 for a in assignments if not a.get("proposed_tags"))
        all_scores  = [s for a in assignments for s in a.get("scores", {}).values()]
        avg_tags    = (
            sum(len(a["proposed_tags"]) for a in assignments) / len(assignments)
            if assignments else 0
        )

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Items processed", f"{len(assignments):,}")
        with col2:
            st.metric("Got ≥1 proposed tag", f"{n_assigned:,}",
                      f"{n_assigned / len(assignments) * 100:.0f}%")
        with col3:
            st.metric("No tags proposed", f"{n_none:,}")
        with col4:
            st.metric("Avg proposed tags", f"{avg_tags:.1f}")

        st.divider()
        col_left, col_right = st.columns(2)

        # ── Tag coverage bar chart ────────────────────────────────────────────
        with col_left:
            st.subheader("Proposed tag coverage")
            tag_counts = Counter(
                tag
                for a in assignments
                for tag in a.get("proposed_tags", [])
            )
            if tag_counts:
                coverage_df = pd.DataFrame(
                    tag_counts.most_common(),
                    columns=["tag", "items"],
                )
                fig = px.bar(
                    coverage_df,
                    x="items",
                    y="tag",
                    orientation="h",
                    labels={"tag": "Tag", "items": "Items assigned"},
                    height=max(400, len(tag_counts) * 24),
                )
                fig.update_layout(
                    yaxis={"categoryorder": "total ascending"},
                    margin=dict(t=20),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No tags proposed across any items.")

        # ── Score distribution ────────────────────────────────────────────────
        with col_right:
            st.subheader("Similarity score distribution")
            if all_scores:
                score_df = pd.DataFrame({"score": all_scores})
                fig = px.histogram(
                    score_df,
                    x="score",
                    nbins=40,
                    labels={"score": "Cosine similarity score", "count": "Assignments"},
                )
                fig.update_layout(margin=dict(t=20))
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    f"{len(all_scores):,} total tag assignments | "
                    f"min {min(all_scores):.3f} · median "
                    f"{sorted(all_scores)[len(all_scores)//2]:.3f} · "
                    f"max {max(all_scores):.3f}"
                )

            # Status breakdown pie
            st.subheader("Assignment mode")
            status_counts = Counter(a.get("status") for a in assignments)
            status_df = pd.DataFrame(
                [(k, v) for k, v in status_counts.items()],
                columns=["status", "count"],
            )
            fig = px.pie(
                status_df,
                values="count",
                names="status",
                color="status",
                color_discrete_map={
                    "overwrite": "#4C72B0",
                    "add_only":  "#55A868",
                    "skipped":   "#C44E52",
                },
            )
            fig.update_layout(margin=dict(t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── Browse assignments ────────────────────────────────────────────────
        st.subheader("Browse assignments")

        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            status_options = ["All"] + sorted({a.get("status", "") for a in assignments})
            status_filter = st.selectbox("Filter by status", status_options)
        with filter_col2:
            tag_filter_asgn = st.text_input("Filter by proposed tag (partial match)", "")

        filtered_asgn = assignments
        if status_filter != "All":
            filtered_asgn = [a for a in filtered_asgn if a.get("status") == status_filter]
        if tag_filter_asgn:
            filtered_asgn = [
                a for a in filtered_asgn
                if any(tag_filter_asgn.lower() in t.lower() for t in a.get("proposed_tags", []))
            ]

        asgn_rows = [
            {
                "title":         a.get("title", "")[:80],
                "type":          a.get("item_type", ""),
                "status":        a.get("status", ""),
                "existing_tags": ", ".join(a.get("existing_tags", [])),
                "proposed_tags": ", ".join(a.get("proposed_tags", [])),
                "final_tags":    ", ".join(a.get("final_tags", [])),
                "top_score":     max(a.get("scores", {}).values(), default=None),
            }
            for a in filtered_asgn
        ]
        asgn_df = pd.DataFrame(asgn_rows)

        st.dataframe(
            asgn_df.reset_index(drop=True),
            use_container_width=True,
            height=500,
            column_config={
                "title":         st.column_config.TextColumn("Title", width="large"),
                "type":          st.column_config.TextColumn("Type", width="small"),
                "status":        st.column_config.TextColumn("Status", width="small"),
                "existing_tags": st.column_config.TextColumn("Existing tags"),
                "proposed_tags": st.column_config.TextColumn("Proposed tags"),
                "final_tags":    st.column_config.TextColumn("Final tags"),
                "top_score":     st.column_config.NumberColumn("Top score", format="%.3f"),
            },
        )
        st.caption(f"Showing {len(filtered_asgn):,} of {len(assignments):,} assignments.")


# ── Tab 6: Browse ─────────────────────────────────────────────────────────────

with tab_browse:
    st.subheader(f"Browse items ({len(filtered):,} shown)")

    title_search = st.text_input("Search by title or creator", "")
    if title_search:
        mask = (
            filtered["title"].str.contains(title_search, case=False, na=False)
            | filtered["creators"].str.contains(title_search, case=False, na=False)
        )
        filtered = filtered[mask]

    display_cols = ["title", "item_type", "creators", "publication_date",
                    "date_added", "tags", "tag_count", "pdf_source"]

    st.dataframe(
        filtered[display_cols].reset_index(drop=True),
        use_container_width=True,
        height=600,
        column_config={
            "title":            st.column_config.TextColumn("Title", width="large"),
            "item_type":        st.column_config.TextColumn("Type", width="small"),
            "creators":         st.column_config.TextColumn("Creators"),
            "publication_date": st.column_config.TextColumn("Pub. date", width="small"),
            "date_added":       st.column_config.TextColumn("Date added", width="small"),
            "tags":             st.column_config.TextColumn("Tags", width="medium"),
            "tag_count":        st.column_config.NumberColumn("# Tags", width="small"),
            "pdf_source":       st.column_config.TextColumn("PDF source", width="small"),
        },
    )
