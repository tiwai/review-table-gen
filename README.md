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

- **State**: Interactive review status marker (`✅` OK, `❌` Bad, blank / Unreviewed). Clicking the cell cycles through the states; preferences are saved in the browser.
- **Subject**: The commit subject line from the input list.
- **Commit ID**: Links to the downstream (expanded) kernel tree commit.
- **kernel-source**: Links to the `kernel-source.git` commit corresponding to the patch.
- **Issues**: Displays the number of open issues found, with resolved issues shown in parentheses `(N fixed)`.
    - **Brackets `[N]`**: Indicates the number of issues unique to the SUSE downstream backport.
    - **Highlighting**: Cells with downstream-only issues (where open issues > 0) are highlighted with a distinct background color.
    - **Asterisk `*`**: Indicates that pre-verified findings are available for this review (with pre-verification background color).
    - **Checkmark `✓`**: Indicates that re-verified findings are available for this review (with re-verified background color).
    - **Dimmed Cells**: Indicates that the review has already been visited in the current browser.
- **Severity**: The estimated severity level of the regression (None, Low, Medium, High). Highlighted with severity colors, and dimmed with `(fixed)` when all findings are resolved.
- **Review Time**: The time spent by the model reviewing the commit, in seconds.

A **Table Legend** is displayed at the bottom of the report to explain all markers, symbols, and highlight colors.

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

- `--list`: Path to the commit list file (format: `sha subject`). Optional if `--update` is specified.
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
- `--update`: Only update review entries modified in the given git commit range (e.g. `ID1..ID2`), commit list file, or list of commit IDs. Split review subpages will only be generated for the specified/modified commits, while the main index table is fully updated. Newly added commits are appended to the report.
- `--update-list`: Commit list file or list of commits to update (alias for `--update`).

## Local Web Service

`review_server.py` serves the same pages dynamically instead of writing static files. It uses only the Python standard library, reuses the loaders and templates from `generate_report.py` (run it from the source tree), and serves multiple branches from a single process. Reviews are read from a dataset directory (git tree access is not supported).

```bash
python3 review_server.py --config server.json [--host 127.0.0.1] [--port 8080] [--ttl 60] \
    [--certfile cert.pem [--keyfile key.pem]] \
    [--log-file server.log] [--log-level debug|info|warning|error]
```

Logs go to stderr, or to the file given by `--log-file` (reopened automatically when rotated by logrotate). `--log-level` sets the minimum level (default: `warning`):
- `error`: Request failures (with tracebacks).
- `warning`: Also malformed or timed-out requests.
- `info`: Also the access log of every request and dropped/failed TLS connections.
- `debug`: Also cache rebuilds with their timing.

The server speaks plain HTTP by default. Pass `--certfile` (and `--keyfile` unless the key is in the same PEM file) to enable HTTPS as well; both `http://` and `https://` are then served on the same port, distinguished by the first byte of each connection. A self-signed certificate can be created with:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout key.pem -out cert.pem -subj /CN=localhost
```

Browsers warn about self-signed certificates unless they are trusted explicitly.

or simply `make serve`. The config file looks like:

```json
{
  "dataset": "kreviews",
  "rows": 50,
  "kerncvs": false,
  "show_review_time": false,
  "branches": {
    "SLE12-SP5": {
      "list": "test/list-SLE12-SP5",
      "models": ["gemma-4", "qwen3.6"],
      "title": "SLE12-SP5 Potential Regressions"
    }
  }
}
```

Relative paths are resolved against the config file location, and `~` is expanded. A relative `list` is looked up in the dataset directory first (e.g. `branches/SLE12-SP5/list`), then relative to the config file. `dataset`, `rows`, `kerncvs` and `show_review_time` can be overridden per branch.

Served URLs:
- `/`: List of branches (redirects if only one branch is configured).
- `/b/<BRANCH>/`: The index table. The branch switcher is generated from the configured branches.
- `/b/<BRANCH>/reviews/<MODEL_DIR>/<xx>/<SHA>/review.html`: Review subpage, read from the dataset on each request.
- `/api/<BRANCH>.json`: The index data as JSON.

The collected index data of each branch is cached for `--ttl` seconds, and rebuilt earlier when the commit list file changes. Append `?reload=1` to any URL to force a rebuild. The server binds to `127.0.0.1` by default; it has no authentication, so be careful when binding to other addresses (use HTTPS, or put a reverse proxy in front).

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
