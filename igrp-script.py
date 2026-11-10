"""IGRP automation helper.

Automates the repetitive parts of the IGRP / SIGE workflow:

    + sign in to the NOSi portal;
    + open "Resumo do dia" (write the daily summary);
    + open "Alunos - Faltas e Notas", pick the class (turma), generate the
      absence list and download the absence report as a PDF;
    + export an Excel grade template for every class/subject and assessment;
    + import the filled template and save the grades in "Atribuir de Notas".

Credentials are read from environment variables (optionally loaded from a
local ``.env`` file) or asked interactively. They are never hard-coded,
printed or logged.

Requirements: Python 3.10+, ``selenium>=4.6`` (Selenium Manager takes care
of the browser driver) and ``openpyxl`` for the grade workbook. See README.md
for setup instructions.
"""

from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from getpass import getpass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover - reported only by options 3 and 4
    Workbook = load_workbook = None  # type: ignore[assignment]
    Alignment = Font = PatternFill = None  # type: ignore[assignment]
    get_column_letter = None  # type: ignore[assignment]

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Load a local .env next to this file, if python-dotenv is installed.
# Real environment variables always win over the file.
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is optional
    pass
else:
    load_dotenv(Path(__file__).with_name(".env"))

Locator = tuple[str, str]

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_LOGIN_URL = "https://nosiapps.gov.cv/redglobal/redglobal.glb_dispatcher.login"
DEFAULT_TIMEOUT = 30

# Class selector on the "Alunos - Faltas e Notas" page.
TURMA_SELECT_ID = "form_1_anoturmadisc"

# Selectors on the "Atribuir de Notas" (grade entry) page.
ANO_LETIVO_SELECT_ID = "form_1_ano_letivo"
PERIODO_SELECT_ID = "form_1_periodo"
AVALIACAO_SELECT_ID = "form_1_tipo_avaliacaodata"
NOTAS_TABLE_ID = "formlist_1"

# Marker written by option 3 and read by option 4.
TEMPLATE_PREFIX = "pautas_"

# Human labels for the "1T"/"2T"/"3T" tags used in the file names.
TRIMESTER_NAMES = {
    "1T": "Primeiro Trimestre",
    "2T": "Segundo Trimestre",
    "3T": "Terceiro Trimestre",
}

MENU = """
====================== IGRP ======================
1 - write summary      (Sala Aula > Resumo do dia)
2 - download absences  (Diretor Turma > Alunos - Faltas e Notas)
3 - grade template     (choose trimester > Excel .xlsx)
4 - import grades      (choose trimester > save in SIGE)
5 - quit
==================================================
"""


class IgrpError(RuntimeError):
    """A recoverable, user-facing error in the automation flow."""


def _env_timeout() -> int:
    raw = os.getenv("IGRP_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = int(raw)
    except ValueError:
        print(
            f"Ignoring invalid IGRP_TIMEOUT={raw!r}; using {DEFAULT_TIMEOUT}s.",
            file=sys.stderr,
        )
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


LOGIN_URL = os.getenv("IGRP_LOGIN_URL", DEFAULT_LOGIN_URL).strip() or DEFAULT_LOGIN_URL
BROWSER = os.getenv("IGRP_BROWSER", "firefox").strip().lower() or "firefox"
TIMEOUT = _env_timeout()
HEADLESS = _env_flag("IGRP_HEADLESS")
TURMA = (os.getenv("IGRP_TURMA") or "").strip()
GRADES_FILE = (os.getenv("IGRP_GRADES_FILE") or "").strip()
GRADES_DRY_RUN = _env_flag("IGRP_GRADES_DRY_RUN")
NOTA_MAX = 20.0


def _nota_max() -> float:
    raw = (os.getenv("IGRP_NOTA_MAX") or "").strip()
    if not raw:
        return NOTA_MAX
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        print(
            f"Ignoring invalid IGRP_NOTA_MAX={raw!r}; using {NOTA_MAX:g}.",
            file=sys.stderr,
        )
        return NOTA_MAX
    return value if value > 0 else NOTA_MAX


def download_dir() -> Path:
    """Resolved download folder (created on demand)."""
    raw = (os.getenv("IGRP_DOWNLOAD_DIR") or "downloads").strip() or "downloads"
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _download_prefs() -> dict[str, object]:
    """Browser preferences that save PDF reports instead of opening them."""
    target = str(download_dir())
    return {
        "browser.download.folderList": 2,
        "browser.download.dir": target,
        "browser.download.useDownloadDir": True,
        "browser.download.manager.showWhenStarting": False,
        "browser.helperApps.neverAsk.saveToDisk": (
            "application/pdf,application/octet-stream,application/x-pdf"
        ),
        "pdfjs.disabled": True,
        "browser.download.always_ask_before_handling_new_types": False,
    }


def _mask(value: str) -> str:
    """Hide most of a value so it is safe to show in the terminal."""
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"


def _href_param(href: str, name: str) -> str:
    """Read a query-string parameter from an href."""
    values = parse_qs(urlparse(href).query).get(name)
    return values[0] if values else ""


def _norm_text(value: str) -> str:
    """Lowercase alphanumerics, accents removed, so '7ªD', '7-D' and '7D' match."""
    composed = unicodedata.normalize("NFKD", value.casefold())
    stripped = "".join(ch for ch in composed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", stripped)


def _school_year_start(today: date) -> date:
    """1 September of the current school year.

    From September onward that is this year; from January to August the school
    year started in the previous year.
    """
    year = today.year if today.month >= 9 else today.year - 1
    return date(year, 9, 1)


def _file_is_stable(path: Path, tries: int = 3) -> bool:
    """True once the file size stops changing (download finished)."""
    last = -1
    for _ in range(tries):
        size = path.stat().st_size
        if size == last and size > 0:
            return True
        last = size
        time.sleep(0.3)
    return False


@dataclass
class GradeSheet:
    """One worksheet: a class/subject in a period, with its assessments."""

    year_label: str
    year_code: str
    period_label: str
    period_code: str
    turma_label: str
    turma_code: str
    assessments: list[tuple[str, str]] = field(default_factory=list)
    students: list[tuple[str, str]] = field(default_factory=list)
    grades: dict[tuple[str, str], str] = field(default_factory=dict)


@dataclass
class ImportStats:
    """Counters shared by the workbook/file import loops."""

    updated: int = 0
    already: int = 0
    skipped: int = 0
    failed: int = 0
    assessments: int = 0
    files: int = 0
    warnings: list[str] = field(default_factory=list)


def _require_xlsx() -> None:
    if Workbook is None:
        raise IgrpError(
            "Excel support needs the 'openpyxl' package. "
            "Install the requirements with: pip install -r requirements.txt"
        )


def _cell_code(value: object) -> str:
    """Normalise a spreadsheet cell into a portal code (no trailing .0)."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalize_grade(raw: object, max_value: float) -> str | None:
    """Turn a spreadsheet cell into the grade string sent to the portal.

    Returns ``None`` for an empty cell (leave the grade untouched), ``""``
    for the clear markers (erase the grade) and the normalised number
    otherwise.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError(f"not a grade: {raw!r}")
    if isinstance(raw, (int, float)):
        text = f"{raw:g}"
    else:
        text = str(raw).strip()
    if not text:
        return None
    if text.casefold() in {"-", "–", "—", "apagar", "limpar", "clear"}:
        return ""
    text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"not a number: {raw!r}") from exc
    if number < 0 or number > max_value:
        raise ValueError(f"outside 0..{max_value:g}: {raw!r}")
    return f"{number:g}"


def _match_option(
    options: list[tuple[str, str]], code: object, label: object
) -> tuple[str, str] | None:
    """Find an option by code first, then by (accent/case-insensitive) label."""
    wanted_code = _cell_code(code)
    if wanted_code:
        for value, text in options:
            if value == wanted_code:
                return value, text
    wanted_label = _norm_text(_cell_code(label))
    if wanted_label:
        for value, text in options:
            if _norm_text(text) == wanted_label:
                return value, text
    return None


def grades_workbook_path(period_short: str = "") -> Path:
    """New timestamped workbook path, optionally tagged with the trimester."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    middle = f"{period_short}_" if period_short else ""
    return download_dir() / f"{TEMPLATE_PREFIX}{middle}{stamp}.xlsx"


def latest_grades_files() -> list[Path]:
    """Workbooks for option 4.

    ``IGRP_GRADES_FILE`` imports a single file. Otherwise the newest file of
    each trimester that has one (``pautas_1T_*.xlsx``, ``2T``, ``3T``) is
    imported, so a full year can be filled and saved trimester by trimester.
    """
    if GRADES_FILE:
        path = Path(GRADES_FILE)
        if not path.is_absolute():
            path = BASE_DIR / path
        if not path.is_file():
            raise IgrpError(f"IGRP_GRADES_FILE does not exist: {path}")
        return [path]

    folder = download_dir()
    files: list[Path] = []
    for index in range(1, 4):
        candidates = sorted(
            folder.glob(f"{TEMPLATE_PREFIX}{index}T_*.xlsx"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            files.append(candidates[0])
    if files:
        return files

    # Backwards compatible with a single untagged workbook.
    candidates = sorted(
        folder.glob(f"{TEMPLATE_PREFIX}*.xlsx"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return [candidates[0]]

    raise IgrpError(
        "No grade workbook found. Run option 3 first or set "
        "IGRP_GRADES_FILE in .env."
    )


def _trimester_tag(path: Path) -> str:
    """Return the '1T'/'2T'/'3T' tag of a workbook name, or ''."""
    match = re.search(r"(\d)T_", path.name)
    return f"{match.group(1)}T" if match else ""


def _choose_grades_files(paths: list[Path]) -> list[Path]:
    """Let the user import a single trimester (default: every one found)."""
    if len(paths) <= 1:
        return paths

    labels: list[str] = []
    for path in paths:
        tag = _trimester_tag(path)
        name = TRIMESTER_NAMES.get(tag)
        if name:
            labels.append(f"{tag} - {name} ({path.name})")
        else:
            labels.append(path.name)

    chosen = _prompt_choice("Trimester workbooks found:", labels)
    if chosen is None:
        return paths
    return [paths[chosen]]


def _sheet_title(sheet: GradeSheet, used: set[str]) -> str:
    """Excel-safe, unique sheet name (max 31 chars)."""
    base = re.sub(r"[\[\]:*?/\\]", "-", sheet.turma_label)
    base = re.sub(r"\s+", " ", base).strip() or "Turma"
    base = base[:31]
    title, counter = base, 2
    while title.casefold() in used:
        suffix = f" ({counter})"
        title = base[: 31 - len(suffix)] + suffix
        counter += 1
    used.add(title.casefold())
    return title


def _write_grade_workbook(
    path: Path, sheets: list[GradeSheet], max_value: float, period_label: str = ""
) -> None:
    """Write one trimester workbook: a 'Leia-me' sheet plus one per class."""
    workbook = Workbook()
    readme = workbook.active
    readme.title = "Leia-me"

    title_font = Font(bold=True, size=14, color="1F4E78")
    heading_font = Font(bold=True, color="FFFFFF")
    heading_fill = PatternFill("solid", start_color="1F4E78", end_color="1F4E78")

    title = "IGRP - Modelo de lançamento de notas"
    if period_label:
        title += f" — {period_label}"
    readme["A1"] = title
    readme["A1"].font = title_font
    readme["A2"] = f"Gerado em {datetime.now():%d-%m-%Y %H:%M}"
    readme["A4"] = "Como usar"
    readme["A4"].font = Font(bold=True)
    instructions = [
        "1. Cada ficheiro corresponde a um trimestre; cada folha a uma turma/disciplina.",
        f"2. Preencha as notas nas células em branco (escala 0 a {max_value:g}).",
        "3. Deixe a célula vazia para manter a nota actual; escreva '-' para apagar.",
        "4. Não altere os nomes das folhas nem a linha de cabeçalhos.",
        "5. Guarde o ficheiro e execute a opção 4 do script.",
    ]
    for row, text in enumerate(instructions, start=5):
        readme.cell(row=row, column=1, value=text)

    meta_header = [
        "Folha",
        "Ano letivo",
        "Código ano",
        "Período",
        "Código período",
        "Turma",
        "Código turma",
    ]
    meta_start = 12
    for col, text in enumerate(meta_header, start=1):
        cell = readme.cell(row=meta_start, column=col, value=text)
        cell.font = heading_font
        cell.fill = heading_fill

    widths = [32, 22, 14, 20, 16, 26, 20]
    for col, width in enumerate(widths, start=1):
        readme.column_dimensions[get_column_letter(col)].width = width

    used: set[str] = set()
    for index, sheet in enumerate(sheets, start=1):
        sheet_name = _sheet_title(sheet, used)
        worksheet = workbook.create_sheet(sheet_name)

        headers = ["Aluno"] + [label for _, label in sheet.assessments]
        headers.append("Código do aluno")
        codes = ["#avaliação →"] + [code for code, _ in sheet.assessments]
        codes.append(None)

        for col, text in enumerate(headers, start=1):
            cell = worksheet.cell(row=1, column=col, value=text)
            cell.font = heading_font
            cell.fill = heading_fill
            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )
        for col, text in enumerate(codes, start=1):
            worksheet.cell(row=2, column=col, value=text)

        for row_index, (student_id, name) in enumerate(sheet.students, start=3):
            worksheet.cell(row=row_index, column=1, value=name)
            for col, (code, _) in enumerate(sheet.assessments, start=2):
                value = sheet.grades.get((student_id, code), "")
                cell = worksheet.cell(row=row_index, column=col, value=value or None)
                cell.alignment = Alignment(horizontal="center")
            worksheet.cell(
                row=row_index,
                column=len(headers),
                value=student_id,
            )

        # Hidden code row (row 2) and hidden student-id column.
        worksheet.row_dimensions[2].hidden = True
        worksheet.column_dimensions[get_column_letter(len(headers))].hidden = True
        worksheet.freeze_panes = "B3"
        worksheet.column_dimensions["A"].width = 42
        for col in range(2, len(headers)):
            worksheet.column_dimensions[get_column_letter(col)].width = 18
        worksheet.sheet_view.showGridLines = True

        readme.cell(row=meta_start + index, column=1, value=sheet_name)
        readme.cell(row=meta_start + index, column=2, value=sheet.year_label)
        readme.cell(row=meta_start + index, column=3, value=sheet.year_code)
        readme.cell(row=meta_start + index, column=4, value=sheet.period_label)
        readme.cell(row=meta_start + index, column=5, value=sheet.period_code)
        readme.cell(row=meta_start + index, column=6, value=sheet.turma_label)
        readme.cell(row=meta_start + index, column=7, value=sheet.turma_code)

    workbook.save(path)


def _read_grade_workbook(path: Path) -> list[dict[str, object]]:
    """Parse the template into plans; never trusts the sheet order."""
    workbook = load_workbook(path, data_only=True)
    if "Leia-me" not in workbook.sheetnames:
        raise IgrpError(
            f"{path.name} was not generated by option 3 (missing 'Leia-me')."
        )

    readme = workbook["Leia-me"]
    metadata: dict[str, dict[str, str]] = {}
    header_seen = False
    for row in readme.iter_rows(values_only=True):
        first = _cell_code(row[0]) if row else ""
        if first.casefold() == "folha":
            header_seen = True
            continue
        if not header_seen or not first:
            continue
        metadata[first] = {
            "year_label": _cell_code(row[1]),
            "year_code": _cell_code(row[2]),
            "period_label": _cell_code(row[3]),
            "period_code": _cell_code(row[4]),
            "turma_label": _cell_code(row[5]),
            "turma_code": _cell_code(row[6]),
        }

    plans: list[dict[str, object]] = []
    for name in workbook.sheetnames:
        if name == "Leia-me":
            continue
        meta = metadata.get(name)
        if not meta:
            continue  # a sheet added by the user; ignore it

        worksheet = workbook[name]
        headers = [
            worksheet.cell(row=1, column=col).value
            for col in range(1, worksheet.max_column + 1)
        ]
        codes = [
            worksheet.cell(row=2, column=col).value
            for col in range(1, worksheet.max_column + 1)
        ]

        code_col = None
        for col in range(2, len(headers) + 1):
            if _norm_text(_cell_code(headers[col - 1])) in {
                "codigodoaluno",
                "codigoaluno",
                "idaluno",
            }:
                code_col = col
                break

        assessments: list[dict[str, object]] = []
        for col in range(2, len(headers) + 1):
            if col == code_col:
                continue
            code = _cell_code(codes[col - 1])
            label = _cell_code(headers[col - 1])
            if code or label:
                assessments.append({"code": code, "label": label, "col": col})

        students: list[dict[str, object]] = []
        for row in range(3, worksheet.max_row + 1):
            student_name = _cell_code(worksheet.cell(row=row, column=1).value)
            if not student_name:
                continue
            values: dict[int, object] = {}
            for assessment in assessments:
                col = int(assessment["col"])
                raw = worksheet.cell(row=row, column=col).value
                if raw is None or (isinstance(raw, str) and not raw.strip()):
                    continue
                values[col] = raw
            if not values:
                continue
            students.append(
                {
                    "id": _cell_code(worksheet.cell(row=row, column=code_col).value)
                    if code_col
                    else "",
                    "name": student_name,
                    "values": values,
                }
            )

        plans.append(
            {
                "sheet": name,
                **meta,
                "assessments": assessments,
                "students": students,
            }
        )
    return plans


def _prompt(label: str) -> str:
    try:
        return input(label).strip()
    except EOFError as exc:  # no interactive terminal (scheduler, pipe, ...)
        raise IgrpError(
            "No interactive terminal available. Set IGRP_USERNAME and "
            "IGRP_PASSWORD in .env or in the environment."
        ) from exc


def _read_password() -> str:
    try:
        return getpass("IGRP password (input hidden): ")
    except (EOFError, OSError):  # no interactive TTY available
        print(
            "WARNING: this terminal cannot hide the password input.",
            file=sys.stderr,
        )
        return _prompt("IGRP password (visible): ")


def _prompt_choice(title: str, labels: list[str]) -> int | None:
    """Numbered choice; returns a 0-based index, or None for "all".

    Empty input and a closed stdin (scheduler, pipe, ...) mean "all", which
    keeps unattended runs working exactly as before.
    """
    if len(labels) <= 1:
        return None

    print(title)
    for index, label in enumerate(labels, start=1):
        print(f"  {index} - {label}")

    for _ in range(3):
        try:
            answer = input("Choice (Enter = all): ").strip()
        except EOFError:  # non-interactive terminal
            print()
            return None
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(labels):
            return int(answer) - 1
        print(
            f"  Invalid choice {answer!r}; type a number from "
            f"1 to {len(labels)}."
        )

    print("  No valid choice; using all.")
    return None


def read_credentials() -> tuple[str, str]:
    """Return (username, password) from the environment or interactive prompts."""
    username = (os.getenv("IGRP_USERNAME") or "").strip()
    password = os.getenv("IGRP_PASSWORD") or ""

    if not username:
        username = _prompt("IGRP username: ").strip()
    if not password:
        password = _read_password()

    if not username or not password:
        raise IgrpError(
            "Username and password are required. "
            "Fill in .env (see .env.example) or answer the prompts."
        )
    return username, password


def build_driver() -> webdriver.Remote:
    """Create the browser session for the configured browser."""
    if BROWSER == "firefox":
        options = webdriver.FirefoxOptions()
        if HEADLESS:
            options.add_argument("-headless")
        for key, value in _download_prefs().items():
            options.set_preference(key, value)
        return webdriver.Firefox(options=options)

    chromium_prefs = {
        "download.default_directory": str(download_dir()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
    }

    if BROWSER in {"chrome", "chromium"}:
        options = webdriver.ChromeOptions()
        if HEADLESS:
            options.add_argument("--headless=new")
        options.add_experimental_option("prefs", chromium_prefs)
        return webdriver.Chrome(options=options)

    if BROWSER in {"edge", "msedge"}:
        options = webdriver.EdgeOptions()
        if HEADLESS:
            options.add_argument("--headless=new")
        options.add_experimental_option("prefs", chromium_prefs)
        return webdriver.Edge(options=options)

    raise IgrpError(
        f"Unsupported IGRP_BROWSER={BROWSER!r}. Use firefox, chrome or edge."
    )


class IgrpScript:
    """Thin wrapper around a Selenium driver for the IGRP/SIGE navigation."""

    def __init__(self, web_driver_arg: webdriver.Remote) -> None:
        self.driver = web_driver_arg
        self.wait = WebDriverWait(self.driver, TIMEOUT)

    # -- low level helpers ------------------------------------------------

    def _clickable(self, locator: Locator):
        return self.wait.until(EC.element_to_be_clickable(locator))

    def _wait_idle(self) -> None:
        """Wait for the portal's full-screen loading overlay to go away."""
        try:
            WebDriverWait(self.driver, TIMEOUT).until(
                lambda d: "loading"
                not in (
                    d.find_element(By.TAG_NAME, "body").get_attribute("class") or ""
                ).split()
            )
        except TimeoutException:
            pass  # not every page toggles the class; never block forever

    def _click(self, *locators: Locator) -> None:
        """Click the first clickable element among the given locators.

        Retries once when a transient loading overlay intercepts the click.
        """
        last_error: Exception | None = None
        for locator in locators:
            try:
                element = self._clickable(locator)
            except TimeoutException as exc:
                last_error = exc
                continue

            for _ in range(2):
                self._wait_idle()
                try:
                    element.click()
                    return
                except ElementClickInterceptedException as exc:
                    last_error = exc
                    try:
                        element = self._clickable(locator)
                    except TimeoutException as wait_exc:
                        last_error = wait_exc
                        break

        raise IgrpError(
            "No clickable element found for any of: "
            + ", ".join(f"{by}={value!r}" for by, value in locators)
        ) from last_error

    def _type(self, locator: Locator, text: str) -> None:
        field = self._clickable(locator)
        field.clear()
        field.send_keys(text)

    def _select_options(self, select_id: str) -> list[tuple[str, str]]:
        """Return the (value, label) pairs of a native <select>.

        The portal re-renders selects after some AJAX calls, so the nodes can
        go stale mid-read; retry instead of aborting the whole run.
        """
        for attempt in range(3):
            try:
                element = self.driver.find_element(By.ID, select_id)
                options: list[tuple[str, str]] = []
                for option in element.find_elements(By.TAG_NAME, "option"):
                    value = (option.get_attribute("value") or "").strip()
                    if not value:
                        continue
                    label = (
                        option.get_attribute("label") or option.text or value
                    ).strip()
                    options.append((value, label))
                return options
            except StaleElementReferenceException:
                if attempt == 2:
                    raise
                time.sleep(0.5)
        return []

    def _select2_value(self, select_id: str, value: str) -> None:
        """Set a Select2-backed <select> and notify the widget."""
        self.driver.execute_script(
            """
            const el = document.getElementById(arguments[0]);
            if (!el) { throw new Error('select not found: ' + arguments[0]); }
            el.value = arguments[1];
            if (window.jQuery) {
                window.jQuery(el).trigger('change');
            } else {
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            select_id,
            value,
        )

    def _set_value(self, element_id: str, value: str) -> None:
        """Set an input value and notify the IGRP framework (jQuery)."""
        self.driver.execute_script(
            """
            const el = document.getElementById(arguments[0]);
            if (!el) { throw new Error('field not found: ' + arguments[0]); }
            el.value = arguments[1];
            if (window.jQuery) {
                window.jQuery(el).trigger('change');
            } else {
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            element_id,
            value,
        )

    def _pick_turma(self) -> tuple[str, str]:
        """Choose the class (turma) to work with."""
        options = self._select_options(TURMA_SELECT_ID)
        if not options:
            raise IgrpError(
                "No 'Ano/Turma' options were found for this account "
                "(is the user a 'Diretor de Turma'?)."
            )

        if TURMA:
            wanted = _norm_text(TURMA)
            for value, label in options:
                if wanted in {_norm_text(value), _norm_text(label)}:
                    return value, label
            available = ", ".join(f"{label} ({value})" for value, label in options)
            raise IgrpError(
                f"IGRP_TURMA={TURMA!r} not found. Available: {available}"
            )

        if len(options) == 1:
            return options[0]

        available = ", ".join(f"{label} ({value})" for value, label in options)
        raise IgrpError(
            "Multiple turmas available; set IGRP_TURMA to one of: " + available
        )

    def _report_link(self):
        """The 'Relatorio' (PDF) link of the 'Relatório das Faltas' panel."""
        return self.driver.find_element(By.CSS_SELECTOR, "a[data-title='Relatorio']")

    def _wait_report_link(self) -> str:
        """Wait until the report link carries the selected class id."""

        def populated(driver) -> bool:
            try:
                link = driver.find_element(
                    By.CSS_SELECTOR, "a[data-title='Relatorio']"
                )
                href = link.get_attribute("href") or ""
            except (NoSuchElementException, StaleElementReferenceException):
                return False
            return bool(_href_param(href, "p_turma_id"))

        WebDriverWait(self.driver, TIMEOUT).until(populated)
        return self._report_link().get_attribute("href") or ""

    def _download_report(self, label: str) -> Path:
        """Click the PDF report link and return the saved file."""
        folder = download_dir()
        before = {p.name for p in folder.iterdir() if p.is_file()}

        main_handle = self.driver.current_window_handle
        link = self._report_link()
        href = link.get_attribute("href") or ""

        self._wait_idle()
        try:
            link.click()
        except WebDriverException:
            # The link sits inside a scrollable panel; a JS click bypasses
            # the "cannot be scrolled into view" restriction.
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});"
                "arguments[0].click();",
                link,
            )

        try:
            path = self._wait_for_new_file(folder, before)
        except IgrpError:
            print("Browser download did not start; fetching the report URL.")
            path = self._fetch_report(href, folder)

        # Close the extra tab opened by target="_blank", if any.
        for handle in list(self.driver.window_handles):
            if handle != main_handle:
                self.driver.switch_to.window(handle)
                self.driver.close()
        if main_handle in self.driver.window_handles:
            self.driver.switch_to.window(main_handle)

        return self._rename_download(path, label)

    @staticmethod
    def _fetch_report(href: str, folder: Path) -> Path:
        """Direct fallback download when the browser does not save the file."""
        if not href:
            raise IgrpError("The report link has no URL.")
        target = folder / f"report_{int(time.time())}.pdf"
        try:
            with urllib.request.urlopen(href, timeout=TIMEOUT) as response:
                data = response.read()
        except OSError as exc:
            raise IgrpError(f"Could not download the report: {exc}") from exc
        target.write_bytes(data)
        return target

    @staticmethod
    def _wait_for_new_file(folder: Path, before: set[str]) -> Path:
        deadline = time.monotonic() + TIMEOUT
        candidate: Path | None = None
        while time.monotonic() < deadline:
            new_files = [
                p
                for p in folder.iterdir()
                if p.is_file()
                and p.name not in before
                and not p.name.endswith((".part", ".tmp", ".crdownload"))
            ]
            if new_files:
                candidate = max(new_files, key=lambda p: p.stat().st_mtime)
                if _file_is_stable(candidate):
                    return candidate
            time.sleep(0.5)
        if candidate is not None:
            return candidate
        raise IgrpError(
            f"The report did not download within {TIMEOUT}s (folder: {folder})."
        )

    @staticmethod
    def _rename_download(path: Path, label: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9]+", "", label) or "turma"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = path.with_name(f"faltas_{safe}_{stamp}{path.suffix or '.pdf'}")
        try:
            path.replace(target)
        except OSError:
            return path
        return target

    # -- flows ------------------------------------------------------------

    def login(self, username: str, password: str) -> None:
        """Sign in and land on the teacher's main menu."""
        self.driver.get(LOGIN_URL)

        self._type((By.ID, "usernameUserInput"), username)
        self._type((By.ID, "password"), password)

        # Autentika SSO submit button ("Entrar"). The old portal used a
        # "btn-block text-uppercase" button; keep it as a last-resort fallback.
        self._click(
            (By.CSS_SELECTOR, "button.btn-autentika-primary"),
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//button[normalize-space()='Entrar']"),
            (
                By.XPATH,
                '//button[contains(@class, "btn-block")'
                ' and contains(@class, "text-uppercase")]',
            ),
        )

        # Portal shell -> open the app -> open the side menu.
        self._click((By.CLASS_NAME, "app-icon"))
        self._click((By.ID, "side-bar-ctrl"))

        # Discipline management -> teacher's main menu.
        self._click((By.LINK_TEXT, "Gestão de Disciplina"))
        self._click((By.LINK_TEXT, "Menu Principal Professor"))

    def write_summary(self) -> None:
        """Open the daily summary page (Sala Aula > Resumo do dia)."""
        self._click((By.LINK_TEXT, "Sala Aula"))
        self._click((By.LINK_TEXT, "Resumo do dia"))

    def get_absence_list(self) -> Path:
        """Pick the class, generate the absence list and download the PDF."""
        self._click((By.LINK_TEXT, "Diretor Turma"))
        self._click((By.LINK_TEXT, "Alunos - Faltas e Notas"))
        self._wait_idle()

        value, label = self._pick_turma()
        self._select2_value(TURMA_SELECT_ID, value)
        self._wait_idle()
        print(f"Class selected: {label}")

        # Reporting period: 1 September of this school year -> today.
        today = date.today()
        start = _school_year_start(today)
        self._set_value("dt_inicio", start.strftime("%d-%m-%Y"))
        self._set_value("dt_fim", today.strftime("%d-%m-%Y"))
        self._wait_idle()
        print(f"Period: {start:%d-%m-%Y} to {today:%d-%m-%Y}")

        # "Pesquisar" generates the absence list for the selected class.
        self._click(
            (By.CSS_SELECTOR, "a[data-title='Pesquisar']"),
            (By.XPATH, "//a[.//span[normalize-space()='Pesquisar']]"),
        )
        self._wait_idle()
        self._wait_report_link()
        print("Absence list generated.")

        return self._download_report(label)

    # -- grade entry (options 3 and 4) ------------------------------------

    def _open_notes_page(self) -> None:
        """Open 'Atribuir de Notas' (the menu entry is hidden until expanded)."""
        if self.driver.find_elements(By.ID, ANO_LETIVO_SELECT_ID):
            return

        links = self.driver.find_elements(
            By.XPATH, "//a[contains(normalize-space(.), 'Atribuir de Notas')]"
        )
        if not links:
            # Return to the teacher menu through the side bar, then retry.
            self._click((By.LINK_TEXT, "Gestão de Disciplina"))
            self._click((By.LINK_TEXT, "Menu Principal Professor"))
            links = self.driver.find_elements(
                By.XPATH, "//a[contains(normalize-space(.), 'Atribuir de Notas')]"
            )
        if not links:
            raise IgrpError("Could not find the 'Atribuir de Notas' menu entry.")

        href = links[0].get_attribute("href")
        if not href:
            raise IgrpError("The 'Atribuir de Notas' entry has no URL.")

        self.driver.get(href)
        self._wait_idle()
        try:
            WebDriverWait(self.driver, TIMEOUT).until(
                EC.presence_of_element_located((By.ID, ANO_LETIVO_SELECT_ID))
            )
        except TimeoutException as exc:
            raise IgrpError("The 'Lançamento das Notas' page did not load.") from exc

    def _selected_option(self, select_id: str) -> tuple[str, str]:
        code = ""
        for attempt in range(3):
            try:
                element = self.driver.find_element(By.ID, select_id)
                code = (element.get_attribute("value") or "").strip()
                break
            except StaleElementReferenceException:
                if attempt == 2:
                    raise
                time.sleep(0.5)
        for value, label in self._select_options(select_id):
            if value == code:
                return code, label
        return code, code

    def _wait_for_option(self, select_id: str, value: str) -> None:
        """Wait until a value exists in a select (options load by AJAX)."""

        def present(driver) -> bool:
            try:
                element = driver.find_element(By.ID, select_id)
                return any(
                    (option.get_attribute("value") or "").strip() == value
                    for option in element.find_elements(By.TAG_NAME, "option")
                )
            except (NoSuchElementException, StaleElementReferenceException):
                return False

        try:
            WebDriverWait(self.driver, TIMEOUT).until(present)
        except TimeoutException as exc:
            available = ", ".join(v for v, _ in self._select_options(select_id))
            raise IgrpError(
                f"Option {value!r} never appeared in {select_id!r}. "
                f"Available: {available or '(none)'}"
            ) from exc

    def _ensure_option(self, select_id: str, value: str) -> None:
        """Select a value only when it is not already selected."""
        current = ""
        for attempt in range(3):
            try:
                element = self.driver.find_element(By.ID, select_id)
                current = (element.get_attribute("value") or "").strip()
                break
            except StaleElementReferenceException:
                if attempt == 2:
                    raise
                time.sleep(0.5)
        if current == value:
            return
        self._select2_value(select_id, value)
        self._wait_idle()
        time.sleep(0.5)

    @staticmethod
    def _turma_allowed(code: str, label: str) -> bool:
        """True when the class matches IGRP_TURMA (or no filter is set)."""
        if not TURMA:
            return True
        wanted = _norm_text(TURMA)
        return wanted in {_norm_text(code), _norm_text(label)}

    def _read_grade_rows(self) -> list[dict[str, object]]:
        """Read the student rows of the currently selected assessment.

        A stale node means the table was repopulated mid-read; returning an
        empty list makes ``_wait_grade_rows`` read again instead of crashing.
        """
        rows: list[dict[str, object]] = []
        try:
            for tr in self.driver.find_elements(
                By.CSS_SELECTOR, f"#{NOTAS_TABLE_ID} tr[row]"
            ):
                data: dict[str, object] = {
                    "name": "",
                    "student": "",
                    "nota": "",
                    "tr": tr,
                }
                for element in tr.find_elements(By.TAG_NAME, "input"):
                    name = element.get_attribute("name")
                    if name == "p_aluno_id_fk":
                        data["student"] = (element.get_attribute("value") or "").strip()
                    elif name == "p_nome_fk":
                        data["name"] = (element.get_attribute("value") or "").strip()
                    elif name == "p_nota_fk":
                        data["nota"] = (element.get_attribute("value") or "").strip()
                if data["student"] or data["name"]:
                    rows.append(data)
        except StaleElementReferenceException:
            return []
        return rows

    def _wait_grade_rows(
        self, timeout: float | None = None
    ) -> list[dict[str, object]]:
        """Wait until the grade table is rendered *and* stable, then read it.

        The portal sometimes clears the table and repopulates it a moment
        later, so two consecutive identical reads are required. An empty
        table is accepted after a short grace period (the caller can retry).
        """
        deadline = time.monotonic() + (TIMEOUT if timeout is None else timeout)
        previous: tuple[tuple[str, str, str], ...] | None = None
        rows: list[dict[str, object]] = []
        zero_since: float | None = None

        while time.monotonic() < deadline:
            rows = self._read_grade_rows()
            signature = tuple(
                (str(row["student"]), str(row["name"]), str(row["nota"]))
                for row in rows
            )
            if signature and signature == previous:
                return rows
            if not signature:
                if zero_since is None:
                    zero_since = time.monotonic()
                elif time.monotonic() - zero_since >= 3:
                    return rows
            else:
                zero_since = None
            previous = signature
            time.sleep(0.5)
        return rows

    def _load_assessment_rows(self, assessment_code: str) -> list[dict[str, object]]:
        """Select an assessment and read its rows, retrying a stuck fragment."""
        rows: list[dict[str, object]] = []
        for attempt in range(3):
            try:
                self._wait_for_option(AVALIACAO_SELECT_ID, assessment_code)
                self._ensure_option(AVALIACAO_SELECT_ID, assessment_code)
                rows = self._wait_grade_rows()
            except StaleElementReferenceException:
                if attempt == 2:
                    raise
                print("    page re-rendered; retrying the assessment read...")
                self._wait_idle()
                time.sleep(1)
                continue
            if rows:
                return rows
            if attempt < 2:
                print(f"    no student rows yet; retrying ({attempt + 2}/3)...")
                self._select2_value(AVALIACAO_SELECT_ID, "")
                self._wait_idle()
                time.sleep(1)
                self._select2_value(AVALIACAO_SELECT_ID, assessment_code)
                self._wait_idle()
                time.sleep(1)
        return rows

    def _prepare_grade_view(
        self,
        year_code: str,
        period_code: str,
        turma_code: str,
        assessment_code: str | None = None,
    ) -> list[dict[str, object]]:
        """Select year/period/class/assessment and return the student rows."""
        self._open_notes_page()
        if year_code:
            self._wait_for_option(ANO_LETIVO_SELECT_ID, year_code)
            self._ensure_option(ANO_LETIVO_SELECT_ID, year_code)
        self._wait_for_option(PERIODO_SELECT_ID, period_code)
        self._ensure_option(PERIODO_SELECT_ID, period_code)
        self._wait_for_option(TURMA_SELECT_ID, turma_code)
        self._ensure_option(TURMA_SELECT_ID, turma_code)
        if assessment_code:
            return self._load_assessment_rows(assessment_code)
        return []

    def _match_live_option(
        self, select_id: str, code: object, label: object
    ) -> tuple[str, str] | None:
        return _match_option(self._select_options(select_id), code, label)

    def _set_grade_field(self, tr, value: str) -> None:
        field = tr.find_element(By.CSS_SELECTOR, "input[name='p_nota_fk']")
        self.driver.execute_script(
            """
            const el = arguments[0];
            el.value = arguments[1];
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            field,
            value,
        )

    def _confirm_grades(self) -> None:
        """Submit the form and wait for the reloaded page."""
        self._wait_idle()
        url_before = self.driver.current_url
        self._click((By.CSS_SELECTOR, "a[data-title='Confirmar']"))
        try:
            WebDriverWait(self.driver, TIMEOUT).until(
                lambda d: d.current_url != url_before
            )
        except TimeoutException:
            pass  # some saves keep the same URL; the wait below still applies
        self._wait_idle()
        time.sleep(1.5)

    def export_grade_template(self) -> list[Path]:
        """Build one Excel template per trimester, with every assessment."""
        _require_xlsx()
        self._open_notes_page()

        year_code, year_label = self._selected_option(ANO_LETIVO_SELECT_ID)
        print(f"School year: {year_label}")
        print("Reading classes and scheduled assessments (this takes a while)...")

        trimesters: dict[str, dict[str, object]] = {}
        periods = self._select_options(PERIODO_SELECT_ID)
        if not periods:
            raise IgrpError("No trimester available in the portal.")

        # Ask which trimester to download (Enter/EOF = every trimester).
        chosen = _prompt_choice(
            "Trimester to download:", [label for _, label in periods]
        )
        if chosen is not None:
            print(f"Only {periods[chosen][1]} will be downloaded.")

        for period_index, (period_code, period_label) in enumerate(periods, start=1):
            if chosen is not None and period_index - 1 != chosen:
                continue
            self._wait_for_option(PERIODO_SELECT_ID, period_code)
            self._ensure_option(PERIODO_SELECT_ID, period_code)
            self._wait_idle()
            time.sleep(1.5)

            sheets: list[GradeSheet] = []
            for turma_code, turma_label in self._select_options(TURMA_SELECT_ID):
                if not self._turma_allowed(turma_code, turma_label):
                    continue
                self._wait_for_option(TURMA_SELECT_ID, turma_code)
                self._ensure_option(TURMA_SELECT_ID, turma_code)
                self._wait_idle()
                time.sleep(3)  # the assessment list is fetched by AJAX

                # Every assessment scheduled for this class is a column.
                assessments = self._select_options(AVALIACAO_SELECT_ID)
                if not assessments:
                    print(f"  {period_label} | {turma_label}: no assessments (skipped)")
                    continue

                students: list[tuple[str, str]] = []
                seen: set[str] = set()
                grades: dict[tuple[str, str], str] = {}

                for assessment_code, _ in assessments:
                    for row in self._load_assessment_rows(assessment_code):
                        student_id = str(row["student"]) or _norm_text(str(row["name"]))
                        if student_id not in seen:
                            seen.add(student_id)
                            students.append((student_id, str(row["name"])))
                        grades[(student_id, assessment_code)] = str(row["nota"])

                sheets.append(
                    GradeSheet(
                        year_label=year_label,
                        year_code=year_code,
                        period_label=period_label,
                        period_code=period_code,
                        turma_label=turma_label,
                        turma_code=turma_code,
                        assessments=list(assessments),
                        students=students,
                        grades=grades,
                    )
                )
                print(
                    f"  {period_label} | {turma_label}: "
                    f"{len(assessments)} avaliação(ões), {len(students)} alunos"
                )

            if sheets:
                trimesters[period_code] = {
                    "index": period_index,
                    "label": period_label,
                    "sheets": sheets,
                }

        if not trimesters:
            if chosen is not None:
                raise IgrpError(
                    f"No class with scheduled assessments was found in "
                    f"{periods[chosen][1]!r}. Create the assessments in SIGE "
                    "first or pick another trimester."
                )
            raise IgrpError(
                "No class with scheduled assessments was found. "
                "Create the assessments in SIGE first."
            )

        written: list[Path] = []
        for info in trimesters.values():
            short = f"{int(info['index'])}T"
            path = grades_workbook_path(short)
            _write_grade_workbook(
                path,
                info["sheets"],  # type: ignore[arg-type]
                _nota_max(),
                str(info["label"]),
            )
            print(
                f"{short} ({info['label']}): "
                f"{len(info['sheets'])} folha(s) -> {path.name}"  # type: ignore[arg-type]
            )
            written.append(path)
        return written

    def import_grades(self) -> str:
        """Read the trimester workbooks and save the grades in SIGE."""
        _require_xlsx()
        paths = _choose_grades_files(latest_grades_files())
        max_value = _nota_max()

        print(f"{len(paths)} trimester workbook(s) to import:")
        for path in paths:
            print(f"  {path}")
        if GRADES_DRY_RUN:
            print("DRY RUN: no grade will be saved.")

        stats = ImportStats()
        for path in paths:
            plans = _read_grade_workbook(path)
            if not plans:
                stats.warnings.append(f"{path.name}: no grade sheets found; skipped.")
                continue
            stats.files += 1
            for plan in plans:
                self._import_plan(plan, max_value, stats)

        if stats.files == 0:
            raise IgrpError(
                "No usable grade sheets were found in: "
                + ", ".join(path.name for path in paths)
            )

        parts: list[str] = []
        if GRADES_DRY_RUN:
            parts.append(f"Dry run: {stats.updated} grade(s) would be written.")
        else:
            parts.append(
                f"{stats.updated} grade(s) written in {stats.assessments} "
                f"assessment(s) across {stats.files} trimester file(s); "
                f"{stats.already} already correct."
            )
        if stats.skipped:
            parts.append(f"{stats.skipped} cell(s) skipped.")
        if stats.failed:
            parts.append(f"{stats.failed} grade(s) failed verification.")
        if stats.warnings:
            parts.append("Warnings:\n  " + "\n  ".join(stats.warnings))
        return "\n".join(parts)

    def _import_plan(
        self, plan: dict[str, object], max_value: float, stats: ImportStats
    ) -> None:
        label = f"{plan['period_label']} | {plan['turma_label']}"
        if not any(student["values"] for student in plan["students"]):
            return  # nothing filled in this sheet
        self._open_notes_page()

        year = self._match_live_option(
            ANO_LETIVO_SELECT_ID, plan["year_code"], plan["year_label"]
        )
        if not year:
            stats.warnings.append(
                f"{label}: school year {plan['year_label']!r} not found; skipped."
            )
            return
        self._ensure_option(ANO_LETIVO_SELECT_ID, year[0])

        period = self._match_live_option(
            PERIODO_SELECT_ID, plan["period_code"], plan["period_label"]
        )
        if not period:
            stats.warnings.append(
                f"{label}: period {plan['period_label']!r} not found; skipped."
            )
            return
        self._wait_for_option(PERIODO_SELECT_ID, period[0])
        self._ensure_option(PERIODO_SELECT_ID, period[0])
        self._wait_idle()
        time.sleep(1)

        turma = self._match_live_option(
            TURMA_SELECT_ID, plan["turma_code"], plan["turma_label"]
        )
        if not turma:
            stats.warnings.append(
                f"{label}: class {plan['turma_label']!r} not found; skipped."
            )
            return
        self._wait_for_option(TURMA_SELECT_ID, turma[0])
        self._ensure_option(TURMA_SELECT_ID, turma[0])
        self._wait_idle()
        time.sleep(3)

        live_assessments = self._select_options(AVALIACAO_SELECT_ID)
        if not live_assessments:
            stats.warnings.append(f"{label}: no assessments in the portal; skipped.")
            return

        # Each workbook column is one scheduled assessment.
        for assessment in plan["assessments"]:
            match = _match_option(
                live_assessments, assessment["code"], assessment["label"]
            )
            if not match:
                stats.warnings.append(
                    f"{label}: assessment {assessment['label']!r} not found; "
                    "column skipped."
                )
                continue
            assessment_code, assessment_label = match

            cells: list[tuple[dict[str, object], str]] = []
            for student in plan["students"]:
                raw = student["values"].get(assessment["col"])
                if raw is None:
                    continue
                try:
                    desired = _normalize_grade(raw, max_value)
                except ValueError as exc:
                    stats.warnings.append(
                        f"{label} | {student['name']} | {assessment_label}: "
                        f"{exc}; cell skipped."
                    )
                    stats.skipped += 1
                    continue
                if desired is None:
                    continue
                cells.append((student, desired))

            if not cells:
                continue

            rows = self._prepare_grade_view(
                year[0], period[0], turma[0], assessment_code
            )
            by_code = {str(row["student"]): row for row in rows}
            by_name = {_norm_text(str(row["name"])): row for row in rows}

            changes: list[tuple[dict[str, object], dict[str, object], str]] = []
            for student, desired in cells:
                row = by_code.get(str(student["id"])) or by_name.get(
                    _norm_text(str(student["name"]))
                )
                if not row:
                    stats.warnings.append(
                        f"{label} | {student['name']}: not in the assessment "
                        "list; skipped."
                    )
                    stats.skipped += 1
                    continue
                if str(row["nota"]).strip() == desired:
                    stats.already += 1
                    continue
                changes.append((row, student, desired))

            if not changes:
                print(f"  {label} | {assessment_label}: already up to date.")
                continue

            if GRADES_DRY_RUN:
                for row, student, desired in changes:
                    print(
                        f"  [dry-run] {label} | {student['name']}: "
                        f"{row['nota']!r} -> {desired!r}"
                    )
                stats.updated += len(changes)
                continue

            for row, student, desired in changes:
                self._set_grade_field(row["tr"], desired)
            self._confirm_grades()
            stats.assessments += 1
            stats.updated += len(changes)

            # Re-read the assessment to prove the grades were persisted.
            rows = self._prepare_grade_view(
                year[0], period[0], turma[0], assessment_code
            )
            by_code = {str(row["student"]): row for row in rows}
            by_name = {_norm_text(str(row["name"])): row for row in rows}
            bad = 0
            for _, student, desired in changes:
                check = by_code.get(str(student["id"])) or by_name.get(
                    _norm_text(str(student["name"]))
                )
                if not check or str(check["nota"]).strip() != desired:
                    bad += 1
            if bad:
                stats.failed += bad
                stats.warnings.append(
                    f"{label} | {assessment_label}: {bad} grade(s) did not persist."
                )
            print(
                f"  {label} | {assessment_label}: "
                f"saved {len(changes)} grade(s)"
                + ("" if not bad else f" ({bad} failed)")
                + "."
            )


def _menu_loop(script: IgrpScript) -> None:
    actions = {
        "1": ("write summary", script.write_summary),
        "2": ("absence report", script.get_absence_list),
        "3": ("grade template", script.export_grade_template),
        "4": ("grade import", script.import_grades),
    }

    while True:
        print(MENU)
        try:
            option = input("Option: ").strip()
        except EOFError:  # non-interactive terminal
            print()
            return

        if option == "5":
            print("Bye.")
            return

        action = actions.get(option)
        if action is None:
            print("Invalid option.\n")
            continue

        label, run = action
        try:
            result = run()
        except IgrpError as exc:
            print(f"Could not finish '{label}': {exc}\n", file=sys.stderr)
        else:
            if isinstance(result, Path):
                print(f"Saved -> {result}\n")
            elif isinstance(result, list):
                for item in result:
                    print(f"Saved -> {item}")
                print()
            elif isinstance(result, str):
                print(result + "\n")
            else:
                print(f"Opened {label}. The browser stays open for you.\n")


def main() -> int:
    try:
        username, password = read_credentials()
    except IgrpError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130

    try:
        driver = build_driver()
    except IgrpError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2
    except WebDriverException as exc:
        print(f"Could not start the browser: {exc}", file=sys.stderr)
        return 2

    script = IgrpScript(driver)
    try:
        # Never hang forever on a page that never finishes loading.
        driver.set_page_load_timeout(TIMEOUT * 2)
        script.login(username, password)
        print(f"Signed in as {_mask(username)}.")
        _menu_loop(script)
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130
    except IgrpError as exc:
        print(f"Login/navigation failed: {exc}", file=sys.stderr)
        return 1
    except WebDriverException as exc:
        print(f"Browser error: {exc}", file=sys.stderr)
        return 1
    finally:
        # Always release the browser and its driver process.
        try:
            driver.quit()
        except WebDriverException:
            pass


if __name__ == "__main__":
    sys.exit(main())
