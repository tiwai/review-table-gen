# Kernel Review Report Generator

A Python-based tool to generate a single, standalone static HTML report for Linux kernel review results. This tool aggregates commit lists and review datasets into an interactive, browser-based dashboard.

## Features

- **Interactive Table**: A paginated view of commits and their review status.
- **Dynamic Configuration**: Adjust the number of displayed rows (20 to 500) directly from the UI.
- **Color Themes**: Support for both Light and Dark modes, with a dynamic switcher at the bottom. The theme preference is saved in the browser.
- **Author Filtering**: Quickly filter results by the author of the review.
- **Rich Visualization**:
    - **Inline Reviews**: Pretty-formatted metadata (Author, Commits, Subjects) and diffs with syntax highlighting and Markdown support.
    - **Automatic Linkification**: Direct links to upstream Linux kernel, downstream kernel, and kernel-source repositories from within the review popup.
    - **Pre-verification Results**: Structured display of findings (Category, Type, Severity, Evidence).
- **Navigation**: Support for both GitHub and SUSE KernCVS links.
- **Standalone**: Generates a single HTML file with all data embedded; no backend server required.
- **Save Functionality**: Allows users to "save" (download) modified review content directly from the browser.

## Requirements

- Python 3.x (No external dependencies required).

## Usage

```bash
python3 generate_report.py \
    --list <COMMIT_LIST_FILE> \
    --dataset "<DATASET_NAME>" <DATASET_DIR> \
    [--dataset "<DATASET_NAME_2>" <DATASET_DIR_2> ...] \
    --branch <BRANCH_NAME> \
    [--rows <ROWS_PER_PAGE>] \
    [--kerncvs] \
    [--output <OUTPUT_FILE>]
```

### URL Parameters

The generated HTML report supports configuration via URL parameters:
- `theme`: `light` or `dark` (e.g., `report.html?theme=dark`)
- `rows`: Number of rows per page (e.g., `report.html?rows=100`)
- `search`: Initial search text for subjects (e.g., `report.html?search=scsi`)

These parameters take precedence over stored preferences and script defaults.

### Arguments

- `--list`: Path to the commit list file (format: `sha subject`).
- `--dataset`: A pair of dataset name and directory. Can be used multiple times.
- `--branch`: The branch name (used in the report title).
- `--rows`: Number of rows per page (default: 50).
- `--kerncvs`: If set, use `kerncvs.suse.de` links instead of GitHub.
- `--output`: Path to the output HTML file (default: `report.html`).

## Dataset Structure

The tool expects review datasets to follow a git-like object storage format:
- Subdirectories `00/` through `ff/`.
- Each subdirectory contains the full 40-character commit ID as a folder name.
- Within each folder:
    - `review-metadata.json` (Required)
    - `review-inline.txt` (Optional, contains diffs/comments)
    - `review-pre-verification.json` (Optional, contains structured findings)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
