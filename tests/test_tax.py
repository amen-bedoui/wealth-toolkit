import pytest
from wealth import tax, planner


def test_params_are_dated_and_sourced():
    p = tax.params()
    assert p["date_validite"] and "service-public" in p["sources"]["assurance_vie"]


def test_cto_flat_tax_2026():
    assert tax.tax_on_gain(100_000, "CTO", 3) == pytest.approx(31_400)   # 12,8 % + 18,6 %


def test_pea_before_and_after_5_years():
    assert tax.tax_on_gain(100_000, "PEA", 3) == pytest.approx(31_400)
    assert tax.tax_on_gain(100_000, "PEA", 6) == pytest.approx(18_600)


def test_assurance_vie_after_8_years_abattement():
    # gain 100 k€, primes 100 k€ : PS 17,2 % sur tout + 7,5 % sur (100k - 4,6k)
    assert tax.tax_on_gain(100_000, "Assurance-vie", 10, 100_000) == pytest.approx(17_200 + 95_400 * 0.075)
    assert tax.tax_on_gain(100_000, "Assurance-vie", 10, 100_000, couple=True) < tax.tax_on_gain(100_000, "Assurance-vie", 10, 100_000)


def test_assurance_vie_before_8_years():
    assert tax.tax_on_gain(10_000, "Assurance-vie", 5, 50_000) == pytest.approx(10_000 * (0.172 + 0.128))


def test_assurance_vie_high_premiums_taxed_more():
    low = tax.tax_on_gain(100_000, "Assurance-vie", 10, 100_000)
    high = tax.tax_on_gain(100_000, "Assurance-vie", 10, 600_000)
    assert high > low


def test_no_tax_on_loss_and_monaco_zero():
    assert tax.tax_on_gain(-5_000, "CTO", 5) == 0
    assert tax.tax_on_gain(1_000_000, "Résident monégasque", 5) == 0


def test_unknown_envelope():
    with pytest.raises(ValueError):
        tax.tax_on_gain(1, "Livret X", 1)


def test_succession_direct_line_matches_service_public_example():
    # service-public.fr : 100 000 € d'abattement, 200 000 € taxables -> 38 194,35 €
    r = tax.inheritance_tax(300_000, "ligne_directe")
    assert r["droits"] == pytest.approx(38_194.35, abs=0.01)


def test_succession_below_allowance_is_zero():
    assert tax.inheritance_tax(90_000, "ligne_directe")["droits"] == 0


def test_succession_allowance_already_used():
    assert tax.inheritance_tax(100_000, "ligne_directe", already_used_allowance=100_000)["droits"] == pytest.approx(
        tax._progressive(100_000, tax.params()["succession_france"]["ligne_directe"]["bareme"]))


def test_monaco_direct_line_exempt_and_third_party_16():
    assert tax.inheritance_tax(1_000_000, "ligne_directe", "Monaco")["droits"] == 0
    assert tax.inheritance_tax(100_000, "tiers", "Monaco")["droits"] == pytest.approx(16_000)


def test_siblings_and_nephews_rates():
    assert tax.inheritance_tax(15_932 + 24_430, "freres_soeurs")["droits"] == pytest.approx(24_430 * 0.35)
    assert tax.inheritance_tax(7_967 + 1000, "neveux_nieces")["droits"] == pytest.approx(550)


def test_progressive_is_continuous_and_monotone():
    b = tax.params()["succession_france"]["ligne_directe"]["bareme"]
    vals = [tax._progressive(x, b) for x in (1e3, 1e4, 1e5, 1e6, 3e6)]
    assert vals == sorted(vals)


def test_net_of_tax_never_exceeds_gross_and_envelope_order():
    w = planner.target_allocation("Dynamique")
    paths = planner.project(w, planner.Scenario(300_000, 10_000), 12, 3000)
    prem = 300_000 + 120_000
    cmp = tax.compare_envelopes(paths, prem, 12, 0.02)
    assert cmp["Résident monégasque"]["P50"] >= cmp["PEA"]["P50"] >= cmp["CTO"]["P50"]
    assert cmp["Assurance-vie"]["P50"] > cmp["CTO"]["P50"]
    assert (tax.net_of_tax(paths, prem, "CTO", 12) <= paths[:, 12]).all()


def test_donation_plan():
    d = tax.donation_plan(500_000, parents=2, years=30)
    assert d["montant_exonere_par_enfant"] == 100_000 * 2 * 3
    assert d["reste_taxable_par_enfant"] == 0
