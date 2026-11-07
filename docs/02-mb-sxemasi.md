# 02. Ma'lumotlar bazasi sxemasi (ER)

Kelishuvlar:
- PK — `bigint` (identity). Tashqariga ko'rinadigan identifikatorlar alohida: `order.number`, `return_request.number`.
- Pul — `numeric(14,2)`, UZS. Payme bilan almashishda tiyinga (×100) o'giriladi.
- Ko'p tilli matnlar — `jsonb`: `{"uz": "...", "uz_cyrl": "...", "ru": "..."}`.
  `uz_cyrl` bo'sh bo'lsa, lotindan avtomatik transliteratsiya qilinadi (qo'lda tuzatish mumkin).
- Hamma jadvallarda `created_at`, `updated_at` bor (diagrammada ko'rsatilmagan).
- Snapshot maydonlar (`*_snapshot`) — buyurtma vaqtidagi holat. Tovar o'zgarsa ham tarix buzilmaydi.

## 1. accounts + geo

```mermaid
erDiagram
    user ||--o{ address : "manzillari"
    user ||--o| courier_profile : "kuryer bo'lsa"
    user ||--o{ device : "push tokenlar"
    user }o--o{ auth_group : "rollar"
    region ||--o{ district : ""
    district ||--o{ address : ""
    district }o--o| courier_zone : "o'z kuryer zonasi"

    user {
        bigint id PK
        varchar phone UK "+998XXXXXXXXX"
        varchar first_name
        varchar last_name
        varchar email "null"
        varchar language "uz | uz_cyrl | ru"
        bool is_active
        bool is_staff
        timestamptz last_login
    }
    address {
        bigint id PK
        bigint user_id FK
        varchar label "Uy, Ish..."
        bigint district_id FK
        varchar settlement "mahalla / qishloq"
        varchar street
        varchar house
        varchar apartment
        varchar entrance
        smallint floor
        varchar elevator "none | passenger | freight"
        varchar intercom
        text landmark "mo'ljal"
        geography location "Point(lng lat)"
        varchar recipient_name
        varchar recipient_phone
        bool is_default
    }
    region {
        bigint id PK
        jsonb name
        varchar soato_code UK
    }
    district {
        bigint id PK
        bigint region_id FK
        jsonb name
        varchar soato_code UK
        varchar bts_city_code "BTS ma'lumotnomasi"
        varchar fargo_city_code
    }
    courier_profile {
        bigint user_id PK
        varchar vehicle_type "car | truck | moto"
        bigint home_warehouse_id FK
        numeric cash_limit "qo'lidagi naqd limiti"
        bool is_active
    }
    device {
        bigint id PK
        bigint user_id FK
        varchar platform "android | ios | web"
        varchar fcm_token UK
    }
```

OTP kodlar bazada saqlanmaydi: Redis'da `otp:{phone}` → `{hash, attempts}`, TTL 120 s.

## 2. catalog

```mermaid
erDiagram
    category ||--o{ category : "parent"
    category ||--o{ product : ""
    brand ||--o{ product : ""
    product ||--o{ product_variant : "SKU"
    product ||--o{ product_image : ""
    category ||--o{ category_attribute : ""
    attribute ||--o{ category_attribute : ""
    attribute ||--o{ attribute_option : ""
    product ||--o{ attribute_value : ""
    product_variant ||--o{ attribute_value : "variantga xos (rang, xotira)"
    attribute ||--o{ attribute_value : ""
    product_variant ||--o{ price_history : ""
    user ||--o{ favorite : ""
    user ||--o{ compare_item : ""
    product ||--o{ favorite : ""
    product ||--o{ compare_item : ""

    category {
        bigint id PK
        bigint parent_id FK "null"
        varchar slug UK
        jsonb name
        varchar icon
        int sort
        bool is_active
    }
    brand {
        bigint id PK
        varchar slug UK
        varchar name
        varchar logo
    }
    product {
        bigint id PK
        bigint category_id FK
        bigint brand_id FK
        varchar slug UK
        jsonb name
        jsonb description
        varchar model_code
        varchar status "draft | active | archived"
        smallint warranty_months
        bool is_bulky "yirik texnika"
        varchar serial_tracking "none | serial | imei | imei2"
        varchar mxik_code "IKPU, fiskal chek uchun"
        varchar package_code
        numeric vat_percent
        numeric rating_avg
        int rating_count
    }
    product_variant {
        bigint id PK
        bigint product_id FK
        varchar sku UK
        varchar barcode
        jsonb name_suffix "128 GB, qora"
        numeric price
        numeric old_price "chizilgan narx"
        numeric cost_price "tannarx, faqat admin"
        numeric weight_kg
        int length_cm
        int width_cm
        int height_cm
        bool is_active
    }
    product_image {
        bigint id PK
        bigint product_id FK
        bigint variant_id FK "null"
        varchar s3_key
        int sort
    }
    attribute {
        bigint id PK
        varchar code UK "screen_size"
        jsonb name
        jsonb group_name "Ekran, Xotira..."
        varchar data_type "number | text | bool | enum"
        varchar unit "dyuym, Vt, l"
        bool is_filterable
        bool is_comparable
    }
    attribute_option {
        bigint id PK
        bigint attribute_id FK
        jsonb value
        int sort
    }
    category_attribute {
        bigint category_id PK
        bigint attribute_id PK
        bool is_required
        int sort
    }
    attribute_value {
        bigint id PK
        bigint product_id FK
        bigint variant_id FK "null"
        bigint attribute_id FK
        bigint option_id FK "enum uchun"
        numeric value_number
        jsonb value_text
        bool value_bool
    }
    price_history {
        bigint id PK
        bigint variant_id FK
        numeric price
        numeric old_price
        varchar source "manual | excel | 1c"
        bigint changed_by FK
    }
    favorite {
        bigint user_id PK
        bigint product_id PK
    }
    compare_item {
        bigint user_id PK
        bigint product_id PK
    }
```

Qo'shimcha: `product_import (id, file_s3_key, status, rows_total, rows_ok, rows_failed, errors jsonb, created_by)` —
Excel import jurnali. Meilisearch indeksi `products_{uz,uz_cyrl,ru}` signallar + Celery orqali yangilanadi.

## 3. inventory

```mermaid
erDiagram
    warehouse ||--o{ stock : ""
    product_variant ||--o{ stock : ""
    warehouse ||--o{ stock_movement : ""
    product_variant ||--o{ stock_movement : ""
    order ||--o{ reservation : ""
    product_variant ||--o{ reservation : ""
    product_variant ||--o{ serial_unit : ""
    warehouse ||--o{ serial_unit : ""

    warehouse {
        bigint id PK
        varchar code UK
        varchar name
        bigint district_id FK
        geography location
        bool is_active
    }
    stock {
        bigint warehouse_id PK
        bigint variant_id PK
        int on_hand
        int reserved
    }
    stock_movement {
        bigint id PK
        bigint warehouse_id FK
        bigint variant_id FK
        int delta
        varchar reason "receipt | sale | return | adjustment | write_off"
        varchar ref_type
        bigint ref_id
        bigint created_by FK
    }
    reservation {
        bigint id PK
        bigint order_id FK
        bigint variant_id FK
        bigint warehouse_id FK
        int qty
        varchar status "active | committed | released"
        timestamptz expires_at "to'lanmagan onlayn buyurtma uchun"
    }
    serial_unit {
        bigint id PK
        bigint variant_id FK
        bigint warehouse_id FK "null - sotilgan"
        varchar serial_number
        varchar imei1 UK
        varchar imei2 UK
        varchar status "in_stock | reserved | sold | returned | defective | written_off"
        timestamptz received_at
    }
```

`available = on_hand - reserved`. Ombordan chiqarish va rezerv `select_for_update` bilan qilinadi.
`serial_unit` uchun `UNIQUE(variant_id, serial_number)` cheklovi bor.

## 4. cart + orders

```mermaid
erDiagram
    user ||--o| cart : ""
    cart ||--o{ cart_item : ""
    product_variant ||--o{ cart_item : ""
    user ||--o{ order : ""
    order ||--o{ order_item : ""
    product_variant ||--o{ order_item : ""
    order_item ||--o{ order_item_unit : "har bir dona"
    serial_unit ||--o{ order_item_unit : ""
    order ||--o{ order_status_history : ""
    order }o--o| promo_code : ""
    order }o--|| warehouse : "jo'natuvchi ombor"
    order ||--o| delivery_quote : "tanlangan quote"

    cart {
        bigint id PK
        bigint user_id FK "null - mehmon"
        uuid guest_token UK
        bigint promo_code_id FK
    }
    cart_item {
        bigint id PK
        bigint cart_id FK
        bigint variant_id FK
        int qty
    }
    order {
        bigint id PK
        varchar number UK "26-0001234"
        bigint user_id FK
        varchar status "created ... delivered"
        varchar payment_method "payme | click | uzum | cash | card_on_delivery | installment"
        varchar payment_status "unpaid | partially_paid | paid | refunded | partially_refunded"
        numeric subtotal
        numeric discount_total
        numeric delivery_fee "mijoz to'laydi"
        numeric lifting_fee "qavatga ko'tarish"
        numeric total
        numeric required_prepayment "avans talabi"
        numeric paid_amount
        numeric cod_amount "eshikda olinadigan"
        jsonb address_snapshot "qavat, lift, koordinata"
        varchar recipient_name
        varchar recipient_phone
        bool lifting_requested
        bigint delivery_quote_id FK
        bigint warehouse_id FK
        bigint promo_code_id FK
        text customer_comment
        varchar cancel_reason
        varchar language
    }
    order_item {
        bigint id PK
        bigint order_id FK
        bigint variant_id FK
        jsonb name_snapshot
        varchar sku
        int qty
        numeric unit_price
        numeric discount
        numeric line_total
        numeric cost_price_snapshot "marja uchun"
        smallint warranty_months
        varchar mxik_code
    }
    order_item_unit {
        bigint id PK
        bigint order_item_id FK
        bigint serial_unit_id FK
        varchar status "assigned | delivered | returned"
    }
    order_status_history {
        bigint id PK
        bigint order_id FK
        varchar from_status
        varchar to_status
        varchar actor_type "system | customer | staff | courier | provider"
        bigint actor_id FK
        text note
    }
```

## 5. payments + installments

```mermaid
erDiagram
    order ||--o{ payment : ""
    payment ||--o{ refund : ""
    payment ||--o{ fiscal_receipt : ""
    refund ||--o| fiscal_receipt : ""
    order ||--o{ installment_application : ""
    installment_partner ||--o{ installment_application : ""

    payment {
        bigint id PK
        bigint order_id FK
        varchar provider "payme | click | uzum | cash | terminal | installment"
        varchar purpose "full | prepayment | cod"
        numeric amount
        varchar status "pending | processing | succeeded | failed | cancelled | refunded"
        varchar provider_txn_id "UK(provider, provider_txn_id)"
        smallint provider_state "Payme state"
        bigint provider_create_time
        bigint provider_perform_time
        bigint provider_cancel_time
        smallint cancel_reason
        bigint collected_by FK "kuryer, naqd uchun"
    }
    refund {
        bigint id PK
        bigint payment_id FK
        bigint return_request_id FK
        numeric amount
        varchar status
        varchar reason
        bigint created_by FK
    }
    payment_webhook_log {
        bigint id PK
        varchar provider
        varchar ip
        jsonb headers
        jsonb body
        bool signature_valid
        jsonb response
    }
    fiscal_receipt {
        bigint id PK
        bigint order_id FK
        bigint payment_id FK
        bigint refund_id FK
        varchar type "sale | prepayment | refund"
        jsonb items "mxik, package_code, vat, narx"
        varchar ofd_receipt_id
        varchar fiscal_sign
        varchar qr_url
        varchar status "pending | sent | failed"
        text error
    }
    installment_partner {
        bigint id PK
        varchar code UK
        varchar name
        jsonb terms "muddatlar, foizlar"
        bool is_active
    }
    installment_application {
        bigint id PK
        bigint order_id FK
        bigint user_id FK
        bigint partner_id FK
        smallint term_months
        numeric monthly_payment
        varchar status "draft | submitted | approved | rejected | signed | cancelled"
        varchar partner_ref
        bytea pii_encrypted "pasport/PINFL - shifrlangan"
    }
```

## 6. logistics

```mermaid
erDiagram
    courier_zone ||--o{ delivery_tariff : ""
    order ||--o{ shipment : ""
    shipment ||--o{ shipment_event : ""
    delivery_quote }o--|| order : ""
    courier_profile ||--o{ courier_route : ""
    courier_route ||--o{ route_stop : ""
    shipment ||--o| route_stop : ""
    shipment ||--o| delivery_handover : "akt"
    delivery_handover ||--o{ handover_photo : ""
    courier_profile ||--o{ courier_cash_entry : ""

    delivery_provider_config {
        varchar code PK "own | fargo | bts"
        bool is_enabled
        int priority
        int timeout_ms
        numeric max_weight_kg
        bool supports_bulky
        bool supports_cod
        bool supports_lifting
        jsonb settings "kalitlar emas - kalitlar env'da"
    }
    courier_zone {
        bigint id PK
        varchar name
        geography polygon
        bool is_active
    }
    delivery_tariff {
        bigint id PK
        bigint zone_id FK
        varchar vehicle_type "car | truck"
        numeric weight_from_kg
        numeric weight_to_kg
        numeric base_price
        numeric lift_price_per_floor "liftsiz"
        numeric lift_price_with_elevator
        smallint eta_days_min
        smallint eta_days_max
    }
    delivery_quote {
        bigint id PK
        uuid public_id UK
        bigint user_id FK
        varchar provider
        jsonb request "QuoteRequest"
        numeric cost "bizga xarajat"
        numeric customer_price "mijozga ko'rsatilgan"
        smallint eta_days_min
        smallint eta_days_max
        int rank
        timestamptz expires_at
    }
    shipment {
        bigint id PK
        bigint order_id FK
        varchar provider
        varchar provider_shipment_id
        varchar tracking_number
        varchar status "normallashtirilgan"
        varchar provider_status "xom"
        numeric cost_quoted
        numeric cost_actual
        numeric cod_amount
        numeric weight_kg
        varchar label_s3_key
        smallint attempt
        bigint courier_id FK "o'z kuryeri"
    }
    shipment_event {
        bigint id PK
        bigint shipment_id FK
        varchar status
        varchar raw_status
        text description
        varchar source "webhook | poll | courier_app | staff"
        timestamptz occurred_at
    }
    courier_route {
        bigint id PK
        bigint courier_id FK
        date route_date
        varchar status "planned | in_progress | done"
    }
    route_stop {
        bigint id PK
        bigint route_id FK
        bigint shipment_id FK
        smallint seq
        tstzrange time_window
        varchar status "pending | picked_up | on_the_way | delivered | refused | returned"
    }
    delivery_handover {
        bigint id PK
        bigint shipment_id FK
        bigint courier_id FK
        varchar result "delivered | refused"
        bool package_opened
        bool powered_on_checked
        jsonb serials_scanned "kutilgan vs skanerlangan"
        bool serials_match
        bool sms_code_verified
        numeric cash_collected
        numeric terminal_collected
        text refusal_reason
        varchar act_pdf_s3_key
        geography location
    }
    handover_photo {
        bigint id PK
        bigint handover_id FK
        varchar kind "package | powered_on | serial | refusal | signature"
        varchar s3_key
    }
    courier_cash_entry {
        bigint id PK
        bigint courier_id FK
        bigint shipment_id FK "null"
        varchar type "collected_cash | collected_terminal | handed_to_cashier | adjustment"
        numeric amount "+ / -"
        bigint confirmed_by FK
    }
```

Kuryer balansi = `SUM(courier_cash_entry.amount)` (faqat `cash`). Kassaga topshirishni kassir tasdiqlaydi.

## 7. warranty + reviews + promotions + notifications

```mermaid
erDiagram
    order_item_unit ||--o| warranty_card : ""
    order ||--o{ return_request : ""
    order_item ||--o{ return_request : ""
    return_request ||--o{ return_photo : ""
    return_request ||--o| shipment : "olib ketish"
    product ||--o{ review : ""
    order_item ||--o| review : "tasdiqlangan xarid"
    review ||--o{ review_photo : ""
    review ||--o{ review_vote : ""
    product ||--o{ question : ""
    question ||--o{ answer : ""
    promotion ||--o{ promotion_target : ""
    promotion ||--o{ promo_code : ""
    promo_code ||--o{ promo_code_usage : ""

    warranty_card {
        bigint id PK
        bigint order_item_unit_id FK
        varchar serial_number
        date starts_at
        date ends_at
    }
    return_request {
        bigint id PK
        varchar number UK
        bigint order_id FK
        bigint order_item_id FK
        bigint serial_unit_id FK
        bigint user_id FK
        varchar type "return | exchange | warranty_repair"
        varchar reason_code
        text description
        varchar status "submitted | approved | rejected | pickup_scheduled | received | inspecting | refunded | repaired | replaced | closed"
        numeric refund_amount
        text resolution_note
    }
    review {
        bigint id PK
        bigint product_id FK
        bigint user_id FK
        bigint order_item_id FK
        smallint rating "1-5"
        text pros
        text cons
        text body
        varchar status "pending | published | rejected"
        text seller_reply
        int helpful_count
    }
    question {
        bigint id PK
        bigint product_id FK
        bigint user_id FK
        text body
        varchar status
    }
    answer {
        bigint id PK
        bigint question_id FK
        bigint user_id FK
        bool is_official
        text body
        varchar status
    }
    promotion {
        bigint id PK
        jsonb name
        varchar kind "percent | fixed | gift"
        numeric value
        numeric min_order_amount
        numeric max_discount
        timestamptz starts_at
        timestamptz ends_at
        int priority
        bool stackable
        bool is_active
    }
    promotion_target {
        bigint id PK
        bigint promotion_id FK
        varchar target_type "all | category | brand | product | variant"
        bigint target_id
    }
    promo_code {
        bigint id PK
        bigint promotion_id FK
        varchar code UK
        int usage_limit
        int per_user_limit
        int used_count
    }
    promo_code_usage {
        bigint id PK
        bigint promo_code_id FK
        bigint user_id FK
        bigint order_id FK
        numeric discount
    }
    notification_template {
        bigint id PK
        varchar code "otp | order_created | status_changed ..."
        varchar channel "sms | push"
        varchar language
        text body
    }
    notification_log {
        bigint id PK
        bigint user_id FK
        varchar phone
        varchar channel
        varchar template_code
        varchar provider_message_id
        varchar status
        text error
    }
```

Bannerlar: `banner (id, placement, image_s3_key jsonb[til], link, starts_at, ends_at, sort)`.

## 8. core

```mermaid
erDiagram
    setting {
        varchar key PK "cod_max_amount, prepayment_percent ..."
        jsonb value
    }
    audit_log {
        bigint id PK
        bigint actor_id FK
        varchar action "view_pii | update | export ..."
        varchar object_type
        bigint object_id
        jsonb changes
        inet ip
    }
```

## Asosiy indekslar va cheklovlar

| Jadval | Indeks / cheklov |
|---|---|
| `user` | `UNIQUE(phone)` |
| `product_variant` | `UNIQUE(sku)`, `INDEX(product_id, is_active)` |
| `stock` | `PK(warehouse_id, variant_id)`, `CHECK(reserved <= on_hand)`, `CHECK(reserved >= 0)` |
| `serial_unit` | `UNIQUE(variant_id, serial_number)`, `UNIQUE(imei1)`, `INDEX(status)` |
| `order` | `UNIQUE(number)`, `INDEX(user_id, created_at DESC)`, `INDEX(status, created_at)` |
| `payment` | `UNIQUE(provider, provider_txn_id)`, `INDEX(order_id)` |
| `shipment` | `UNIQUE(provider, provider_shipment_id)`, `INDEX(status)` |
| `address`, `warehouse` | GiST `location`; `courier_zone` — GiST `polygon` |
| `review` | `UNIQUE(order_item_id)` — bitta xaridga bitta sharh |
