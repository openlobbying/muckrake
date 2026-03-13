library(tidyverse)
library(rvest)

# https://registrarofconsultantlobbyists.org.uk/

##----------------------------------------------------------------
##                      Download Excel files                     -
##----------------------------------------------------------------

orcl_links_raw <- read_html(
  "https://orcl.my.site.com/CLR_Annual_Returns_Downloads"
) |>
  html_elements(".downloadDropdown li a")

orcl_links <- tibble(
  title = orcl_links_raw |> html_text(),
  link = orcl_links_raw |> html_attr("href")
) |>
  mutate(
    date = janitor::make_clean_names(title),
    date = sub(".*_(.*)_(\\d{4})", "\\1_\\2", date),
    date = lubridate::my(date) %m-% months(2),
    ext = tools::file_ext(link),
    ext = ifelse(ext == "", "csv", ext)
  )

for (i in 1:nrow(orcl_links)) {
  file_path <- paste0(
    "data/raw/orcl/",
    orcl_links$date[i],
    ".",
    orcl_links$ext[i]
  )

  if (!file.exists(file_path)) {
    if (orcl_links$date[i] == as.Date("2024-10-01")) {
      # Q4 2024 and Q1 2025 data are incorrect, but they've uploaded the correct version for Q4 2024 separately
      download.file(
        "https://registrarofconsultantlobbyists.org.uk/wp-content/uploads/2025/01/October-to-December-2024-QIR-Report-Excel-44Kb.xlsx",
        "data/raw/orcl/2024-10-01.xlsx",
        method = "curl"
      )
    } else {
      download.file(
        orcl_links$link[i],
        file_path,
        method = "curl"
      )
    }

    Sys.sleep(1)
  }
}

##----------------------------------------------------------------
##                          Read in data                         -
##----------------------------------------------------------------

read_orcl <- function(file) {
  print(file)

  file_date <- stringr::str_replace_all(
    file,
    "data/raw/orcl/|.xlsx|.csv",
    ""
  ) |>
    as.Date()

  if (file_date <= as.Date("2015-10-01")) {
    orcl_df <- readxl::read_excel(file, skip = 8) |>
      mutate(date = file_date, file = file) |>
      select(date, lobby_firm = 3, org = 2, file = file)
  } else if (file_date <= as.Date("2017-01-01")) {
    orcl_df <- readxl::read_excel(file, skip = 7) |>
      mutate(date = file_date, file = file) |>
      select(date, lobby_firm = 1, org = 2, file = file)
  } else if (file_date <= as.Date("2020-10-01")) {
    orcl_df <- readxl::read_excel(file, skip = 10) |>
      mutate(date = file_date, file = file) |>
      select(date, lobby_firm = 1, org = 2, file = file)
  } else if (file_date <= as.Date("2021-10-01")) {
    orcl_df <- readxl::read_excel(file, skip = 7) |>
      mutate(date = file_date, file = file) |>
      select(date, lobby_firm = 1, org = 2, file = file)
  } else if (file_date <= as.Date("2022-10-01")) {
    orcl_df <- readxl::read_excel(file, skip = 2) |>
      mutate(date = file_date, file = file) |>
      select(date, lobby_firm = 1, org = 2, file = file)
  } else if (file_date <= as.Date("2024-07-01")) {
    orcl_df <- read_csv(file) |>
      mutate(date = file_date, file = file) |>
      select(date, lobby_firm = 1, org = 2, file = file)
  } else if (file_date == as.Date("2024-10-01")) {
    orcl_df <- readxl::read_excel(file) |>
      mutate(date = file_date, file = file) |>
      select(date, lobby_firm = 1, org = 2, file = file)
  } else if (file_date <= as.Date("2025-01-01")) {
    orcl_df <- read_csv(file) |>
      mutate(date = file_date, file = file) |>
      select(date, lobby_firm = 1, org = 2, file = file)
  }

  return(orcl_df)
}

orcl_raw <- list.files(
  path = "data/raw/orcl/",
  pattern = '*.xlsx|*.csv',
  full.names = T
) |>
  map(~ read_orcl(.x)) |>
  bind_rows() |>
  identity()

orcl <- orcl_raw |>
  select(-file) |>
  # combine dates into a listcol
  # group_by(org, lobby_firm) |>
  # reframe(dates = c(date)) |>
  # ungroup() |>
  identity()


##----------------------------------------------------------------
##              Unique lobbyist-org relationships             -
##----------------------------------------------------------------
orcl_unique <- orcl_raw |>
  select(org, lobby_firm) |>
  distinct() |>
  mutate(
    region = "United Kingdom",
    source = "ORCL",
    source_link = "https://orcl.my.site.com/"
  )

write_csv(orcl, paste0("data/processed/orcl.csv"))

rm(orcl_links_raw, orcl_links, i, read_orcl, orcl_raw, orcl_unique, file_path)
