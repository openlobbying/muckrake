library(tidyverse)

iw <- read_csv("data/datasets/gb_meetings/resources/iw_uk.csv") |>
    mutate(date = lubridate::dmy(date))

df <- iw |>
    mutate(organisation_length = nchar(organisation)) |>
    arrange(desc(organisation_length))

View(iw)

iw |>
    count(department, sort = TRUE) |>
    View()