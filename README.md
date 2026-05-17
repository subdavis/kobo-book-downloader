![kobodl logo](docs/kobodl.png)

![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/subdavis/kobo-book-downloader/build.yml?branch=main&style=for-the-badge)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/subdavis/kobo-book-downloader?style=for-the-badge)

# kobodl

This is a **golang rewrite** of [kobo-book-downloader](https://github.com/TnS-hun/kobo-book-downloader), a command line tool to download and remove Digital Rights Management (DRM) protection from media legally purchased from [Rakuten Kobo](https://www.kobo.com/). The resulting [EPUB](https://en.wikipedia.org/wiki/EPUB) files can be read with, amongst others, [KOReader](https://github.com/koreader/koreader).

> **NOTE:** You must have a Kobo email login. See "I can't log in" in the troubleshooting section for how to work around this requirement.

## Features

kobodl preserves the features from [TnS-hun/kobo-book-downloader](https://github.com/TnS-hun/kobo-book-downloader).

* stand-alone; no need to run other software or pre-download through an e-reader.
* downloads `.epub` formatted books

It adds several new features.

* **audiobook support**; command-line only.
  * Use `kobodl book get`. There will not be a download button in the webpage for audiobooks because they consist of many large files.
* **multi-user support**; fetch books for multiple accounts.
* **web interface**; browser GUI for listing users and downloading books.
* **wishlist**; view your Kobo wishlist from the command line.
* [docker image](https://github.com/subdavis/kobodl/pkgs/container/kobodl)
* [pre-built binaries](https://github.com/subdavis/kobo-book-downloader/releases/latest) for Linux, macOS, and Windows.
  * The purpose of the Go rewrite was to get fast native binaries.

## Alternatives to kobodl

Some people prefer `kobodl` because it's **standalone**, which means you don't need other proprietary software like Adobe Digital Editions or Kindle for PC (that I can't use on Linux). However, there is also a way to do this with [Calibre](https://github.com/kovidgoyal/calibre) and 2 plugins:

* [Leseratte10/acsm-calibre-plugin](https://github.com/Leseratte10/acsm-calibre-plugin) - A plugin that can read Adobe Digital Editions files that Kobo web download produces.
* [Satsuoni/DeDRM Tools](https://github.com/Satsuoni/DeDRM_tools) - The (latest fork) popular DRM removal plugin.

Now you can just download the `.acm` file from your book list on Kobo.com and load it into Calibre desktop! It **doesn't work with audiobooks**.

## Web UI

WebUI provides most of the same functions of the CLI. It was added to allow other members of a household to add their accounts to kobodl and access their books without having to set up any tooling.

### User page

![Example of User page](docs/webss.png)

### Book list page

![Example of book list page](docs/books3.png)

## Installation

### Pre-built binaries

No installation necessary. Download the archive for your platform from [the latest release](https://github.com/subdavis/kobo-book-downloader/releases/latest), extract it, and run the binary.

```bash
# Linux (amd64)
curl -L https://github.com/subdavis/kobo-book-downloader/releases/latest/download/kobodl_linux_amd64.tar.gz | tar xz
./kobodl
```

```bash
# macOS (Apple Silicon)
curl -L https://github.com/subdavis/kobo-book-downloader/releases/latest/download/kobodl_darwin_arm64.tar.gz | tar xz
./kobodl
```

```bash
# macOS (Intel)
curl -L https://github.com/subdavis/kobo-book-downloader/releases/latest/download/kobodl_darwin_amd64.tar.gz | tar xz
./kobodl
```

```powershell
# Windows — download kobodl_windows_amd64.zip from the release page and extract it
```

### docker

```bash
# list users
docker run --rm -it \
  -v ${HOME}/.config/kobodl.json:/home/kobodl.json \
  ghcr.io/subdavis/kobodl \
  --config /home/kobodl.json user list

# run web UI
docker run --rm -it \
  -p 5000:5000 \
  -v ${HOME}/.config/kobodl.json:/home/kobodl.json \
  -v ${PWD}:/home/downloads \
  ghcr.io/subdavis/kobodl \
  --config /home/kobodl.json \
  serve \
  --output-dir /home/downloads
```

[Also see the **docker-compose** example file.](./docker-compose.yml)

## Usage

> **Note**: These are commands you type into a shell prompt like Terminal (Ubuntu, macOS) or PowerShell or CMD (Windows). You may need to replace `kobodl` with `./kobodl`, `./kobodl.exe`, or the full path to the extracted binary, depending on your platform.

```bash
# Get started by adding one or more users
kobodl user add

# List users
kobodl user list

# Remove a user
kobodl user remove email@domain.com

# List books
kobodl book list

# List books for a single user
kobodl book list --user email@domain.com

# List all books, including those marked as read/archived
kobodl book list --read

# Show your Kobo wishlist
kobodl book wishlist

# Download a single book (default output directory: ./kobo_downloads)
kobodl book get c1db3f5c-82da-4dda-9d81-fa718d5d1d16

# Download multiple books at once
kobodl book get c1db3f5c-82da-4dda-9d81-fa718d5d1d16 a2ec4g6d-93eb-5eeb-ae92-gb829e6e2e27

# Download a single book with advanced options
kobodl book get \
  --user email@domain.com \
  --output-dir /path/to/download_directory \
  --format-str '{Title}' \
  c1db3f5c-82da-4dda-9d81-fa718d5d1d16

# Download ALL books with default options
kobodl book get --get-all

# Download ALL books with advanced options
kobodl book get \
  --user email@domain.com \
  --output-dir /path/to/download_directory \
  --format-str '{Title}' \
  --get-all

# Download books organized into subdirectories by author
kobodl book get \
  --output-dir /path/to/library \
  --format-str '{Author}/{Title}' \
  --get-all
```

### Format string options

The `--format-str` option supports the following fields:
- `{Author}` - Book author(s)
- `{Title}` - Book title
- `{RevisionId}` - Full revision ID
- `{ShortRevisionId}` - First 8 characters of the revision ID (useful for avoiding filename collisions)

Use `/` in the format string to organize books into subdirectories:
- `'{Author}/{Title}'` creates `Author Name/Book Title.epub`
- `'{Author} - {Title} {ShortRevisionId}'` creates `Author Name - Book Title a1b2c3d4.epub` (default)

### Running the web UI

```bash
kobodl serve
# kobodl web UI listening on http://localhost:5000

# Custom port
kobodl serve --port 8080

# Custom download directory
kobodl serve --output-dir /path/to/downloads
```

### Global options

```bash
# argument format
kobodl [OPTIONS] COMMAND [ARGS]...

# set table output format: simple (default), grid, csv, markdown
kobodl --fmt grid COMMAND [ARGS]...

# set config path (default: $XDG_CONFIG_HOME/kobodl.json)
kobodl --config /path/to/kobodl.json COMMAND [ARGS]...

# enable debug output
kobodl --debug COMMAND [ARGS]...
```

## Troubleshooting

> Some of my books are missing!

Try `kobodl book list --read` to show all "finished" and "archived" books. You can manage your book status on [the library page](https://kobo.com/library). Try changing the status using the "..." button.

> I see a message about "skipping _____" when I download all.

Try to download the book individually using `kobodl book get <revision-id>`, replacing `revision-id` with the UUID from the list table.

> Something else is going wrong!

Try enabling debug output. Run `kobodl --debug book get` (for example). My email address can be found on my [github profile page](https://github.com/subdavis). Do not post account details in a public issue.

## Development

Requires either [mise](https://mise.jdx.dev/) or directly install [Go](https://go.dev/).

```bash
git clone https://github.com/subdavis/kobo-book-downloader
cd kobo-book-downloader
mise install # https://mise.jdx.dev/

# Build
go build -o kobodl .

# Run tests
go test ./...

# Run (without building a binary)
go run .
```

## Notes

kobo-book-downloader uses the same web-based activation method to login as the Kobo e-readers. You will have to open an activation link—that uses the official [Kobo](https://www.kobo.com/) site—in your browser and enter the code. You might need to login if kobo.com asks you to. Once kobo-book-downloader has successfully logged in, it won't ask for the activation again. kobo-book-downloader doesn't store your Kobo password in any form; it works with access tokens.

Credit recursively to [kobo-book-downloader](https://github.com/TnS-hun/kobo-book-downloader) and the projects that lead to it.

## FAQ

**How does this work?**

kobodl works by pretending to be an Android Kobo e-reader. It initializes a device, fetches your library, and downloads books as a "fake" Android app.

**Why does this download KEPUB formatted books?**

Kobo has different formats that it serves to different platforms. For example, Desktop users generally get `EPUB3` books with `AdobeDrm` DRM. Android users typically get `KEPUB` books with `KDRM` DRM, which is fairly easy to remove, so that's what you get when you use this tool.

**Is this tool safe and okay to use?**

I'm not a lawyer, and the discussion below is strictly academic.

The author(s) of `kobodl` don't collect any information about you or your account aside from what is made available through metrics from GitHub, Docker Hub, etc. See `LICENSE.md` for further info.

Kobo would probably claim that this tool violates its [Terms of Use](https://authorize.kobo.com/terms/termsofuse) but I'm not able to conclusively determine that it does so. Some relevant sections are reproduced here.

> The download of, and access to any Digital Content is available only to Customers and is intended only for such Customers' personal and non-commercial use. Any other use of Digital Content downloaded or accessed from the Service is strictly prohibited

This tool should only be used to download books for personal use.

> You may not obscure or misrepresent your geographical location, forge headers, use proxies, use IP spoofing or otherwise manipulate identifiers in order to disguise the origin of any message or transmittal you send on or through the Service. You may not pretend that you are, or that you represent, someone else, or impersonate any other individual or entity.

This might be a violation. This client announces itself to Kobo servers as an Android device, which can safely be construed as "manipulating identifiers", but whether or not the purpose is to "disguise the origin" is unclear.

> Kobo may also take steps to prevent fraud, such as restricting the number of titles that may be accessed at one time, and monitoring Customer accounts for any activity that may violate these Terms. If Kobo discovers any type of fraud, Kobo reserves the right to take enforcement action including the termination or suspension of a User's account.

In other words, you could have your account suspended for using `kobodl`. **Please open an issue on the issue tracker if this happens to you.**
