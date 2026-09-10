# Kernel Review Report Generator

A Python-based tool to generate a single, standalone static HTML report for Linux kernel review results. This tool aggregates commit lists and review datasets into an interactive, browser-based dashboard.

## Features

- **Interactive Table**: A paginated view of commits and their review status.
- **Dynamic Configuration**: Adjust the number of displayed rows (20 to 500) directly from the UI.
- **Color Themes**: Support for both Light and Dark modes, with a dynamic switcher at the bottom. The theme preference is saved in the browser.
- **Author Filtering**: Quickly filter results by the author of the review.
- **Branch Switching**: Dropdown switcher to jump directly to other branch report pages, configured via a JSON config file.
- **Rich Visualization**:
    - **Inline Reviews**: Pretty-formatted metadata (Author, Commits, Subjects) and diffs with syntax highlighting and Markdown support. Supports both plain-text and structured JSON inline review formats with severity/confidence highlighting.
    - **Fix Patches**: If a `review-fix-patches.diff` is provided and issues are found, a "Fix Patch" button appears to show suggested fixes in a pretty diff format.
    - **Automatic Linkification**: Direct links to upstream Linux kernel, downstream kernel, and kernel-source repositories from within the review popup.
    - **Pre-verification Results**: Structured display of findings (Category, Type, Severity, Evidence).
- **Navigation**: Support for both GitHub and SUSE KernCVS links.
- **Split Pages & Standalone Modes**: By default, generates a lightweight index table HTML page, with each detailed commit review outputted to a self-contained subpage under the `reviews/` directory (following the database's subdirectory structure). Clicking any review cell redirects to the specific subpage, with full `localStorage` theme-syncing and visited-tracking. Alternatively, can generate a single giant standalone HTML report with all data embedded (original behavior) using `--single-page`.
- **Standalone Subpages**: Each generated review subpage is self-contained (all styles and scripts are inlined) and can be opened locally via the `file://` protocol with no external dependencies.
- **Data Compression**: Embedded index/review data is compressed (zlib/deflate) to significantly reduce the HTML file size.
- **Save Functionality**: Allows users to "save" (download) modified review content directly from the browser.

## Review Table

The generated report features a comprehensive table with the following columns:

- **Subject**: The commit subject line from the input list.
- **Commit ID**: Links to the downstream (expanded) kernel tree commit.
- **kernel-source**: Links to the `kernel-source.git` commit corresponding to the patch.
- **Issues**: Displays the number of potential issues found.
    - **Brackets `[N]`**: Indicates the number of issues unique to the SUSE downstream backport.
    - **Highlighting**: Cells with downstream-only issues (where total issues > 0) are highlighted with a distinct background color.
    - **Asterisk `*`**: Indicates that pre-verified findings are available for this review.
- **Severity**: The estimated severity level of the regression (None, Low, Medium, High).
- **Review Time**: The time spent by the model reviewing the commit, in seconds.

## Requirements

- Python 3.x.
- Python dependencies listed in `requirements.txt`.
- A modern web browser (Chrome 103+, Firefox 113+, Safari 16.4+) for viewing reports (required for decompression support).

## Installation

```bash
pip install -r requirements.txt
```

## Usage

Using direct file system access:

```bash
python3 generate_report.py \
    --list <COMMIT_LIST_FILE> \
    --dataset <DATABASE_DIR> \
    --model <MODEL_DIR_NAME> \
    [--model <MODEL_DIR_NAME_2> ...] \
    --title "<REPORT_TITLE>" \
    [--rows <ROWS_PER_PAGE>] \
    [--kerncvs] \
    [--target-git <TARGET_GIT_REPO_PATH>] \
    [--output <OUTPUT_FILE>]
```

Using git repository tree access:

```bash
python3 generate_report.py \
    --list <COMMIT_LIST_FILE> \
    --git <GIT_REPO_PATH> \
    [--git-commit <COMMIT_ID>] \
    --model <MODEL_DIR_NAME> \
    [--model <MODEL_DIR_NAME_2> ...] \
    --title "<REPORT_TITLE>" \
    [--rows <ROWS_PER_PAGE>] \
    [--kerncvs] \
    [--target-git <TARGET_GIT_REPO_PATH>] \
    [--output <OUTPUT_FILE>]
```

### URL Parameters

The generated HTML report supports configuration via URL parameters:
- `theme`: `light`, `dark`, or `psychedelic` (e.g., `?theme=dark`)
- `rows`: Number of rows per page (e.g., `?rows=100`)
- `search`: Initial search text for subjects (e.g., `?search=scsi`)
- `author`: Initial author filter (e.g., `?author=Name%20Surname`)
- `severity`: Initial severity filter: `all`, `low`, `medium`, or `high` (e.g., `?severity=high`)

These parameters take precedence over stored preferences and script defaults.

### Arguments

- `--list`: Path to the commit list file (format: `sha subject`).
- `--dataset`: Path to the database directory containing model subdirectories. Exclusive with `--git`.
- `--git`: Path to the git repository containing model subdirectories directly at its root commit tree. Exclusive with `--dataset`.
- `--model`: The subdirectory name of the model to include (e.g., `gpt-oss`, `gemma-4`). Can be used multiple times.
- `--git-commit`: The git commit ID, branch, or tag to read from when `--git` is provided (default: `HEAD`).
- `--title`: The report title.
- `--rows`: Number of rows per page (default: 50).
- `--kerncvs`: If set, use `kerncvs.suse.de` links instead of GitHub.
- `--links-file`: Path to a JSON configuration file containing branch to URL mappings for the branch switcher (e.g., `test/branches.json`).
- `--target-git`: Path to the git repository for the target code being reviewed. If provided, the actual diff/patch of each commit will be extracted and embedded into the report.
- `--output`: Path to the output HTML file (default: `report.html`).
- `--single-page`: If set, generates a single giant standalone HTML report where all review content is embedded and displayed inside modal popups (original behavior), instead of creating split subpages under `reviews/`.

## Dataset Structure

The tool expects review datasets to follow a git-like object storage format:
- Subdirectories `00/` through `ff/`.
- Each subdirectory contains the full 40-character commit ID as a folder name.
- Within each folder:
    - `review-metadata.json` (Required)
    - `review-inline.json` (Optional, contains structured JSON inline review findings, preferred over `review-inline.txt` if present)
    - `review-inline.txt` (Optional, fallback contains plain-text diffs/comments/findings)
    - `review-pre-verification.json` (Optional, contains structured findings)
    - `review-fix-patches.diff` (Optional, contains suggested fix patches)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
