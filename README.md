# Kernel Review Report Generator

A Python-based tool to generate a single, standalone static HTML report for Linux kernel review results. This tool aggregates commit lists and review datasets into an interactive, browser-based dashboard.

## Features

- **Interactive Table**: A paginated view of commits and their review status.
- **Dynamic Configuration**: Adjust the number of displayed rows (20 to 500) directly from the UI.
- **Color Themes**: Support for both Light and Dark modes, with a dynamic switcher at the bottom. The theme preference is saved in the browser.
- **Author Filtering**: Quickly filter results by the author of the review.
- **Branch Switching**: Dropdown switcher to jump directly to other branch report pages, configured via a JSON config file.
- **Rich Visualization**:
    - **Inline Reviews**: Pretty-formatted metadata (Author, Commits, Subjects) and diffs with syntax highlighting and Markdown support.
    - **Fix Patches**: If a `review-fix-patches.diff` is provided and issues are found, a "Fix Patch" button appears to show suggested fixes in a pretty diff format.
    - **Automatic Linkification**: Direct links to upstream Linux kernel, downstream kernel, and kernel-source repositories from within the review popup.
    - **Pre-verification Results**: Structured display of findings (Category, Type, Severity, Evidence).
- **Navigation**: Support for both GitHub and SUSE KernCVS links.
- **Standalone**: Generates a single HTML file with all data embedded; no backend server required.
- **Data Compression**: Embedded review data is compressed (zlib/deflate) to significantly reduce the HTML file size.
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
- `--output`: Path to the output HTML file (default: `report.html`).

## Dataset Structure

The tool expects review datasets to follow a git-like object storage format:
- Subdirectories `00/` through `ff/`.
- Each subdirectory contains the full 40-character commit ID as a folder name.
- Within each folder:
    - `review-metadata.json` (Required)
    - `review-inline.txt` (Optional, contains diffs/comments)
    - `review-pre-verification.json` (Optional, contains structured findings)
    - `review-fix-patches.diff` (Optional, contains suggested fix patches)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
