#!/usr/bin/env python3
"""Install NetCash savings-page UI on the existing Django project.
Only touches four templates and one new CSS file. No database changes.
Provides automatic backups and refuses to overwrite unfamiliar edited templates.
"""
from pathlib import Path
import base64
import zlib
import shutil
from datetime import datetime

PAYLOADS = {'netcash_savings.css': 'eNqVV1tvqzgQfj+/wlK1UnsUOFzMJaCVVjrv+3IeV/tg8BC8ARsZp2kW9b+vTSABQpKuKrWEzmfP5ZtvJj++oz9B/SRtiVryzviuRTXhZAc1cIUa/dAiwatTiqjQj1wolJeE7wC1JZFAUUb4XsPQz1+/bPT9xzeb55aBIfNQAqH6nx1lbVORU1JU8JGSiu24xRTUbZLrW0Cm/xxaxYqTlQv9kaukbUgOVgbqCMDTHWkSV0KdGrh1lPqj+ZXWRO4YtzKhlKgT1w60zefcgT3L9yA7BR/KUpLwthCyTg5NAzInLaQVKH2/Ze7Tfia2szXXaC+slv0LiR15cnxxBLYrVRI5TpqLSsjkxQ1jjGHhhu2vuKGYqqCbHRNcjvEd378ckzgLKIU2l6xRTPBuAERBFMXZCLCxvg85aAkkucG089ybVNqhiWmlCvP0rh+H7Ezx7lhqYJ81SLhYsc6JpF1G8v1OigOnyUtRFGkmJAWZuM0HakXFKHqBHKAIhn9YUpPl0CYubj70qw9LM4yKY+IgXyPMWyR3GXnF4SZwNpG/sR0cvKXiHWRRabuSUQp8xZEh/Q2hhoyaKK4pEXJtz/wdbx9pNPEOCqfA6SyBj5n6NKnnAkQrFLk6isqgG8mwpN4aKBP0NAnOm8S2MGe8OagNmr0zDdFHI0WFnhq0UEH+0MK0mhYG0h0ZVWXiOs5vlwxmlcj3aa2bpTxHhB1d6tF1O+jLYsd9UZ5yh24pAFlwJ9bnDV2CMQ6DIhUHVTFuaMphLR1JIfJD+zQpz83OqXluNybobNkN/o+S4sc+JnP2mx9/JL/nblwv3oTuxnb9t0VAt27/pU4N/J6XkO/1mX8PRSEHJS5FYdzkx7qpjfPo8EuVJwDX1dVcA1Ukg6qbk2DK69Bxppq7NfVfiCpeYXMJVdNNcD1vRomMou1FIi0lmju6TDItDBOmXvpOi4piOamsvqWTWmtLBWtopMq50AVFWJDRj9ALcUQeT5RYh//1ARVo9K38Xpsojvv+fyxsWyCFsx4NvUrJV8RxNU9j9IEX4DBfv8eoFlIyqUirrLxkFTV3z69buiihmA3RUA/RUf7PGkv46ViCvHjgYz/CdHFMfVBAZ8zxJ9SJSUzJ8uaGVVcGDx1zb5m5lML3ez0LY7lYKoK1pWIuZJEWsqdTthEtU+wdxsVAK4Pjw0w7ARchbBe4I5HcrGUDbBuF2Dgwl1yf4uUqYvY+OaIy7HvYX6AghmyB4nDQxK5GWIjDKKJzH6mmUngD25FpbGSLM//GSecmNqgbdR2H/qUZ+g47k3So01jvII63ZO0UxCYk8frBOoKIS+IsXg62uWatTfn2UGur01QxDJeItHam8NqxV9cLKOw2ejcqtoWzMYKSFeHb2gTMoKDFcnvyJiP1vA3cLMrefc9Qq/V9srGfIxui9mKf+O6Eym6/fM5kFt8eXbBK5/v+lwDg9LwXxbdL/upRwyNUuou1deIiF3lr02dhbVlmHJ4xjsF4X8FkB502vUgPMAeZ8bk6HM3SWxPtfT9Q4uDOPJTi2C1L4t6mDaQUciZTeMLAPNSrAsxSP5T1jxooI69XR0LjyFv3bHM04NX5tnk8Jwai3/+2cK7R58M0b75QuM3/KZThhBnpn18D3fd0/A47ZWzP0VZvQOrz89t/Y0pZoQ==',
 'savings_account_form.html': 'eNqtVc1u2zAMvu8pCAFFgQGOMay9OR7W7rJLd+gDGIrM1EJkyZOYdkGWdx8lO6nitD0NSGSHfx/5kWL2V4B/CG0bQDzuwg9J8k4GLFd8LDrqjYCrw6f9FRgnWwgkSatJsjJObYA0GWTJrwEtPMpnbZ8CfFfKbS3BX3hAupehY3PGGD1yb8b2slEhsLQy2m7Ao1mKQDuDoUMkAZ3H9VKwxwR+zdalRVIctgkj4IJl1xzi2/Pyi6jfA1POcqUUZVWrn0EZGcJSWFUM8glF/QlgJu9Qthw/qUbl+HZhuNFqg17UlT4KNaMVkUXwmj/FizQGqfhacJUIPRacaFXqes5ZqMocprvJUBLXok5UP+DL3LUqu5uT45D5tRiU1wNpZ0V971ESgoSJO5BTs9bOg7TcEh2IFeyvma1FVQ5T+a+JVfK1LVtv4HqK1UyxGsMxYkPEMYsVWeBv4bYUCSgCMj+t9LuPOJPeu5fC4JrmrN3JOHouI02m9h1TnLVHSd8CP7nEPv3IOjozO5Jcdbf1cYx/2ugoI3/M8W2dM/FGhJVrd+LUiOjKmVPn2qUYXCCR2Y8J8Vx6Z04uAEyrCn7dkNtwq3leM4Vex071C+tss9Zo2gaZJp9uUJaMNOgJ0lm00j7F6dzv33E9HMaSxpvDCOeQcTKSPWibIuT6Cw5STdy4rJ5kZeQKTXTnsdmP8Ra6bVjQjKrD4YKapBgTT/ZHw4mHJBtPj7+32mPLqUEVBh7kKRTxjjkx8Lkqoy4vtCpT0PNkj4AMdS7PcDs0QxOjz5hPe8MMWdavlh8RnZGd2pLITv5vNphhkjzhjA7n0WOg8z7lmyVhXVrNEKSKQx+gp+LmrJ/Vakvk7Px6D1738VID7QbkPb5d9Zo+uuKqQ7WZ3+5pRZ3W2oh1Bv8/F9C9tArNtELeoKoq4yzOluD0Mj1mfzn/ABswVjU=',
 'savings_account_list.html': 'eNqdV81u3DYQvucpBgQMXywLbR0UCLQqEgdFe4hbxP1BTwtKnLUIU5RKUnYWdi55o75Sn6RD6sdcrXbtBvB6peFw5uPMNzPchxPATw61sMCut/Y9d/wdt5gW9O+8crVicPL51cMJqIYLsI47WQ6SQjXlLTjpFJLkmt9JfWPhbVk2nXYWHuEK3SW3FamS/V473kl+DV+X1pI0U1LfgkG1YtZtFdoK0TGoDG5WjHYMjk9JO9XoSjK7tr3Hc5Kdkokf7lbfsPyQs7LRdErnZZmQd1Aqbu2K6TJp+Q2y/BXATF4hF2Q/LPWL/dOe4q0sb9GwPJOjUJK3xEcQjKS/5J4rhS75LqFTItSYENAslTn8KDXXpeQKPnBNOGqCmKWxq+oi8hRizfJ5qLO0upg2tJG+QFsa2TrZaJb3HmhV+jgMwQM+2DiDgivCgvTEtQBKjba89FvteZa2QxSesM2CMKiyCQcfFwungT5J0zl//KQ1suZmGyW3MwpOB0DryPFaSet8ao/FtiKdxmznof3tyQz81KtkKT+M7hlUQ5jWpUHu8DlMXIg5nl9a1DBL3ARoCuvwsE/GkhsBdZFcsMXo++WkaMT2Kf6bxtTk31WNWLEbX0x9NA6fbYp2ZHgjlfPcHqzuOd5IVCJaJgXFC1SxCgFJgpABPa/Y4C+xyE1ZsZyKQBDnRipmaVDesSl12zmQYm9z5CfoMHDbFqmJDMua19HbHVcdvT48QC9Z/92h2cJnOnKreIlVowQSwiE/oLu6QHM21MwZNAY6i8YbjUMSF+xyhJKk6Jyj+oCFUgmb+vURfVfU0rFDHD3CvP5cc/JdB2mW9k52/PJnCL9Hink5WyQIIsD6iBZdVGWz0GSpp8L/YfwRsg+tMKte52O2PhISI3w3fJ1ntiVGPe2pO4dk7rIzZqn7ZanXzw+0N8cLhYlB21La5N1T7rOwsqPmExweYoI4P0vyzBn6VBPeq8CuLCWRF18Gko2vk1GakglNNJa/6/vzpP8zDTTCROemjjRJr2lQdnZ69W0HxfT6NlCvf009nLSHFkH1XSRmCBGD0jZGCuRUp35sR3p+r8l3BF4k9lJBdKMx/TCaOR+ZphsqxCkRTizZirb1NbluTUM9CsPWxT3zQMLmnjhby4JqHYJQN/eGtyz/98s/sf2eKuthLD5u6ALkPIG5e/PtYXc7J9O642oth0StDSVqz87JIUMzUciE3EzGbUg0rFbAfFaJlf4aNYt1K5XyjGwbK4NO3usOYV5ygWrZya8UO6oZ+AON3MiSh0vFEZf33OhwfVra+BX+L1VjqYSPeBRc3/hZ1WsedWHxiB2NHV1C1A5JByATQftrJiGd1YBvaM/TcGRc5KAJhbrm7lEQS96wDyDO4C92hGhfw4+9PUtXIVsv3dd2auUFd7fxpjTikeKZSxN+KiufwUQ0SnEzn2HvMZAYUvhTukoYfr8zafbTu3TW5anwu+Z3XCrftY+x5qX5Dp11t4Ni3brtUr8MzGiUd7pi39NJd0dd2PfiXxZ9oK6avfFGHbzT4rwfbwHwEkYtfKOPQJJSPA3o1YdoeYAPX7OfX/8B+9t51A==',
 'savings_transaction_form.html': 'eNqtVs1u4zYQvu9TDAQEAQrIwm7THhayF5vkvIemQI8CRY0swhSpkqNkDa8vfaO+Up+kI0pKKK0TbIECtizM3/dx/ujTFeBXQlN5SB6O/l6QuBUes5Ifm4ZancDV+d3pCrQVFXgSpOQkKbWVByBFGlnyIB6V2Xv43QnjhSRlDXyDL0h3wjdszRCjQ+zM0E4U0nuW5lqZAzjU28TTUaNvECmBxmG9Tdhjwr5m68wgSQ5b+BF0w7JrDvHpcfs+2b0GJq3hg9Igyyv1CFIL77eJkWkn9pjs3gGs5A2KiuMH1agc374zPCh5QJfscjULFaOlQxLBKf6k+FU2wuwxrazWwqV8WIQWU+abZ2oHc/o+S2l7Qz7PYrTmJgILGU9299hZrwisgz8UNZUTT3nW3Dz7dJFLhV461Q1FSXa/obSuAgFT9oCiktUcjhrlQYxENnnWTcd/YZSLl7L0TsP1FKmYnAqtPA0FSWYOJRngb2p7Gk6eeuZgKuGOb+VMOGefUo01rdN1K4bOs1G2RCjfTHFVHj5Um0rhqqiSkdr3bRuoXCguM4B9+vOzbqmVVqe+TX9lVsuQbU/IaBM/+NK3JbqRXmxZP3EmWlVazcan03PS5zwaC+fz5BY3xH9jcacV9/2Po8tgX3TO1opn+wcZvP/wKn7v3DB4t0ILI3GK5slZs9/989ffMfRoWpSj6bea1w4N5RP08UNgMrkt5yNqzeh1SSaq/0XdPFd588suXmL3SEJpbjGWL1EvxChtdYx7ZaDOfUuNrbYJzysl37UlbyVndeQEwGMlvasLsgc0w75aqFQ9TGm7MdYUtUJdFciD4sIOjSgJjY4gPNNqWD0uFPmy61zjcXcywhp02AvBA1RYEu3S4vLI8fAszhXstChRry2DMBkC81I5jUgbVRUsKEaH83mkHzSzaMpGkI1Ph3/2ymHF9CD3nTAzEvFd85yHn7iPWBcfN89C0DXdGZLB1poIu0HdFQPCqgbhDtFdxPzF8u2UR2kPJQppDxEuFpuBgjwgjQ7L+EOgdcWW8xzwLlmucMax8NBSerOqbl72RNasl37nVNivQMcO+Xbvy1bRW4tfNigP653/ENzi/xd5NuKtSPyfl9PdsIX0dL28krg8G1r4rV00vUw/q/8n/wJFAwWh',
 'savings_transaction_list.html': 'eNqtV91q5DYUvt+nEIIwN3GGtlkKweOS7hJa6C4lWSi9GjTWmViNLLuSPNkhCSx9hr5IX2mfpEeS7ZE9ntlkW5gfSzo639H5+Y78cELgowXFDaE3W/OWWfYjMzBf4c9ZYUtJycnTq4cTIivGibHMirydWckqvyNWWAk4c8M2Qt0a8kEzZVhuRaUMeSTvwb5hpkBxxAg74t2IrdkyNwZnUynUHdEgF9TYrQRTAFhKCg3rBcUdLfgMpecKbI5qlyagnuHcDFX8sFl8Q7NDYHml8KTWzaVcbEgumTELqvKkZrdAs1eEjOYLYBz1+6WwGJ72BO9EfgeaZqnoJgWiJc6LRAv8JPAxL5i6hYRXUjKd4GGBlJCgvelcZORKKKZywSR5xxSaU6Kl6TxGLM4jQO92mk15PZ0X5/2mOtrDweRa1E6IZtewEXBPONSVEfaU3AtbcM3umTwlTGGog+ZEoM80GEuc9o2w27N0Xrf+2Jk3ckdrCe3NYN3iyiqC36RqrPNAUmtRMr2NwtxoSWYt+pLledUou5TCWBfgYx5G0yXY5LuxazsfXQZd6B82sr992I9/zjQn5So5p5PHdMvJquLb3UHXlS4jibWQ6D6K1tii4gt66zI6eGf/sHYXxOjAreY98LUAyaNlFJBsBTIWQWMSP0kJPi9ohJAYYDovMIX8P7GDDPKbBrqFqhtLBJ9UEmF6OUrstgas43ZZsTIabZhscPjwQMLM8s8G9JY8PVFSS5ZDUUkOaO01rDH1VA6YkSF2p6TSiCWwNmLHxGUy7SfSPSSJs+w/uC1sj+rNH3XKYwYk5Psu8wpaj4TnsfNiLain8hXbeY1ml1KOohUkjm57G+qcEkw6sSbBNuBLZwFZLMisFXA51y0GHkXpk6esXX4W1m89lRyG28kcQtxJPAv055anDkN2EocAu/UpuHQedrwo6ZJk1Vjr+uAEJfpNYX3MjT0ntkXUrEqM3BHmC2U05r0rzz3pPIAMcA/SsQFUzY8Q8jRHXYMB2/PqnnvSuSupl5DuEb5tO19avB5U4U9oTKW32PxeZ6mpmYr2lQ2Gmma/MOsaWVw7ZC20i7jbkB3oZ5atJCSYGTVuEJsdeaR+ZSDmIu0fYnqy7hqRpVbjt8h6VkvnOHIzbWPqx288wfXDD55fwqAHw4tTgpmLbFAO9uIFbqf4Bm9MjQnDuYOfB1Mi01z3ilMD442xIsJCSYQa+grvTYMCRI2DCTfF95yPaYRXsgev8kx3h1+qplyBRtLvnW/5F9X5Y6vqXrN6p3N0Vzjr7gyq+rL2QzpCj1nWusIODl7PtILRFGnZxyuNa2WKZ8eeqgUyu/t3Aj7Retb1h5jCAnkUbUizhwAV3LIAGJPuEUwDR7U1aIvcBWjPsj4sEf2OfTvt73H+k/U9clYpVnhlIIPs+PzXPx0+8yXyuMZXGOuIiNmLbw+H9GiuxUfhWGqP7ueCviP8lPxOigtBLulXZovxxeqjdllj4m2APy9JOulnZUmE8qtzvbo9BnLPtPLvP63sSyGu4Q/fZmek5ZR48YphaR09I3cvTDqq9LC5T5//IzmDzkcOa9ZIezH7/Onv2dclqKfYIZVCWdvtFG/6PKukw1jQ77GbDRud33es4ztWitt+6Pjvq+61bdTkMP/5WWhv3u4pUxV3xB/ZikJxd8Cha2zTXbz9G715/wsA5yjQ'}

PROJECT = Path(__file__).resolve().parent
TEMPLATE_DIR = PROJECT / "SysDataBase" / "templates" / "SysDataBase"
CSS_PATH = PROJECT / "static" / "css" / "netcash_savings.css"
BACKUP_ROOT = (PROJECT / ".git" if (PROJECT / ".git").is_dir() else PROJECT) / "netcash_savings_ui_backups"


def build():
    if not (PROJECT / "manage.py").is_file():
        raise SystemExit("ERROR: Move this installer beside manage.py in your BankingSys folder.")
    if not (TEMPLATE_DIR / "base.html").is_file():
        raise SystemExit("ERROR: Could not find SysDataBase base.html. No files changed.")

    old_templates = {}
    for name in PAYLOADS:
        if not name.endswith(".html"):
            continue
        path = TEMPLATE_DIR / name
        if not path.is_file():
            raise SystemExit(f"ERROR: Missing {path}. No files changed.")
        old = path.read_text(encoding="utf-8-sig")
        new = zlib.decompress(base64.b64decode(PAYLOADS[name])).decode("utf-8")
        if old == new:
            continue
        # Avoid replacing templates that teammates may already have redesigned.
        if '{% extends "SysDataBase/base.html" %}' in old or "<html" not in old.lower():
            raise SystemExit(f"STOPPED SAFELY: {name} is already customized. No files changed. "
                             "Use the downloadable HTML templates to merge changes manually.")
        if name.endswith("_list.html") and '<table border="1"' not in old:
            raise SystemExit(f"STOPPED SAFELY: Unexpected {name} layout. No files changed.")
        if name.endswith("_form.html") and "{{ form.as_p }}" not in old:
            raise SystemExit(f"STOPPED SAFELY: Unexpected {name} form. No files changed.")
        old_templates[path] = old

    desired_css = zlib.decompress(base64.b64decode(PAYLOADS["netcash_savings.css"])).decode("utf-8")
    if CSS_PATH.exists() and CSS_PATH.read_text(encoding="utf-8-sig") != desired_css:
        raise SystemExit("STOPPED SAFELY: static/css/netcash_savings.css already exists with different content. No files changed.")

    if not old_templates and CSS_PATH.is_file():
        print("Already installed. Nothing to change.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = BACKUP_ROOT / stamp
    for path in old_templates:
        backup_target = backup / path.relative_to(PROJECT)
        backup_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_target)

    for path in old_templates:
        path.write_text(zlib.decompress(base64.b64decode(PAYLOADS[path.name])).decode("utf-8"),encoding="utf-8")
        print("Updated:", path.relative_to(PROJECT))

    CSS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSS_PATH.write_text(desired_css,encoding="utf-8")
    print("Installed stylesheet:", CSS_PATH.relative_to(PROJECT))
    print("Backups:", backup if old_templates else "Not required (no templates changed)")
    print("No migrations or banking-logic changes. Next: python manage.py check")


if __name__ == "__main__":
    build()
