from src.label_qa import answer


def test_answer_is_quoted_from_the_cited_page():
    a = answer("What is the pre-harvest interval for Delegate WG on apples?")
    assert a.status == "answered" and a.pdf_page == 30 and a.quote_verified
    assert "7 days of harvest" in a.quote


def test_crop_matters():
    apples = answer("What is the most Imidan 70-W I can apply on apples in total per crop season?")
    pears = answer("What is the most Imidan 70-W I can apply on pears in total per year?")
    assert "22 1/8 lb" in apples.quote and "16 lb" in pears.quote


def test_refuses_unknown_product_and_missing_crop():
    assert answer("What is the pre-harvest interval for Altacor on apples?").status == "refused"
    assert answer("What is the pre-harvest interval for Intrepid 2F?").status == "refused"


def test_bc_question_prefers_west_of_rockies_rule():
    a = answer("What is the re-entry interval for Imidan 70-W on apples in BC?")
    assert "West of the Rockies" in a.quote and "7 days" in a.quote
