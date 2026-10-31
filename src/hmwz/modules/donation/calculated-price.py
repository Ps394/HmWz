"""
Preise für Spenden werden basierend auf bestimmten Kriterien berechnet.

_start_timestamp = Startzeitpunkt
_end_timestamp = Endzeitpunkt
_rushed_hours = Beschluenigte Stunden

_base_price = 667 # 24H
    


"""
import HmLogger
import math

HmLogger.setup_logging(HmLogger.logging.INFO)

log = HmLogger.get_logger(__name__)

def qs_donation_price(rushed_hours, donation_hours):
    if donation_hours == 24:
        base_price = 667
    elif donation_hours == 8:
        base_price = 223
    elif donation_hours == 1:
        base_price = 28
    else:
        raise ValueError("Unsupported donation hours")
    
    price_multiplier : float = 1

    block_hours : int = 24
    stage_1 : int = 72
    stage_2 : int = 144

    new_rushed_hours : int = rushed_hours + donation_hours

    if rushed_hours < stage_1 - block_hours:
        price_multiplier = 1
    elif rushed_hours < stage_1:
        if new_rushed_hours > stage_1:
            price_multiplier = 1 + (rushed_hours - (stage_1 - block_hours)) / block_hours
        else:
            price_multiplier = 1
    elif rushed_hours <= stage_2 - block_hours:
        price_multiplier = 2
    elif rushed_hours < stage_2:
        if new_rushed_hours > stage_2:
            price_multiplier = 2 + (rushed_hours - (stage_2 - block_hours)) / block_hours
        else:
            price_multiplier = 2
    else:
        price_multiplier = 3

    return math.ceil(base_price * price_multiplier)

if __name__ == "__main__":
    log.info("---- Stage 1 ----")
    log.info(qs_donation_price(48, 24)) # 667
    log.info(qs_donation_price(48, 8)) # 223
    log.info(qs_donation_price(48, 1)) # 28
    log.info("---- Stage 1 ---- Special Cases")
    log.info(qs_donation_price(48+2, 24)) # 723
    log.info(qs_donation_price(48+2, 8)) # 242
    log.info(qs_donation_price(48+10, 24)) # 945
    log.info(qs_donation_price(48+10, 8)) # 316
    log.info("---- Stage 2 ----")
    log.info(qs_donation_price(72, 24)) # 1334
    log.info(qs_donation_price(72, 8)) # 445
    log.info(qs_donation_price(72, 1)) # 56
    log.info("---- Stage 2 ---- Special Cases")
    log.info(qs_donation_price(120+2, 24)) # 1390
    log.info(qs_donation_price(120+2, 8)) # 465
    log.info(qs_donation_price(120+23, 24)) # 1612
    log.info(qs_donation_price(120+23, 8)) # 539
    log.info("---- Stage 3 ----")
    log.info(qs_donation_price(144, 24)) # 2001
    log.info(qs_donation_price(144, 8)) # 667
    log.info(qs_donation_price(144, 1)) # 84