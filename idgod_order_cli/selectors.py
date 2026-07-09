"""CSS/name selectors for idgod.ph Django order form."""

SELECTORS = {
    "first_name": "#id_first_name",
    "middle_name": "#id_middle_name",
    "last_name": "#id_last_name",
    "date_of_birth": "#id_date_of_birth",
    "state": "#id_state",
    "height_feet": "#id_height_feet",
    "height_inches": "#id_height_inches",
    "weight": "#id_weight",
    "eyes": "#id_eyes",
    "hair": "#id_hair",
    "gender": "#id_gender",
    "address1": "#id_address1",
    "address2": "#id_address2",
    "city": "#id_city",
    "zip": "#id_zip",
    "picture": "#id_picture",
    "signature": "#id_signature",
    "custom_license_number": "#id_custom_license_number",
}

# Cart/checkout form at /cart (scraped 2026-07-09)
CART_SELECTORS = {
    "name": "#id_name",
    "phone": "#id_phone_number",
    "address": "#id_address",
    "city": "#id_city",
    "state": "#id_state",
    "zip": "#id_zip",
    "country": "#id_country",
    "email": "#id_email",
    "payment_method": "#id_payment_method",
    "priority": "#id_priority",
    "coupon": "#id_coupon",
    "captcha": "#id_captcha_1",
}

CART_BUTTONS = {
    "update": 'button[name="action"][value="update"]',
    "finish": 'button[name="action"][value="finish"]',
}

# Default shipping: 20 business days $20
DEFAULT_SHIPPING_VALUE = "9"

PAYMENT_LABELS = {
    "bitcoin": "Bitcoin",
    "litecoin": "Litecoin",
    "card": "Credit/Debit Cards, Apple Pay & Google Pay",
    "apple": "Credit/Debit Cards, Apple Pay & Google Pay",
    "google": "Credit/Debit Cards, Apple Pay & Google Pay",
}

SHIPPING_ALIASES = {
    "standard": "20 days $20",
    "economy": "20 days $20",
    "20": "20 days $20",
    "express": "order moved up Express shipping",
    "50": "order moved up Express shipping",
    "super": "$120 10 PEOPLE OR LESS",
    "120": "$120 10 PEOPLE OR LESS",
    "group": "$200 10-30 PEOPLE",
}
