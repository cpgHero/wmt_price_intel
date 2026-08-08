INSERT INTO retailer(id, display_name, country) VALUES
('walmart_us','Walmart (US)','USA'),
('aldi_us','ALDI','USA'),
('amazon_us_same_day','Amazon Same Day (US)','USA'),
('kroger_us','Kroger','USA'),
('target_us','Target','USA'),
('safeway_us','Safeway','USA'),
('albertsons_us','Albertsons','USA'),
('heb_us','H-E-B','USA')
ON CONFLICT (id) DO NOTHING;

INSERT INTO retailer_alias(alias,retailer_id) VALUES
('Walmart','walmart_us'),('walmart','walmart_us'),('walmart.com','walmart_us'),('Walmart (US)','walmart_us'),
('ALDI','aldi_us'),('aldi','aldi_us'),('aldi.us','aldi_us'),('new_aldi','aldi_us'),
('amazon','amazon_us_same_day'),('amazon.com','amazon_us_same_day'),('Amazon (US)','amazon_us_same_day'),
('kroger','kroger_us'),('Kroger','kroger_us'),
('Target','target_us'),('Safeway','safeway_us'),('Albertsons','albertsons_us'),('H-E-B','heb_us')
ON CONFLICT (alias) DO UPDATE SET retailer_id=excluded.retailer_id;
