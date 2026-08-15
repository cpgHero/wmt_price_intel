INSERT INTO retailer(id, display_name, country) VALUES
('walmart_us','Walmart (US)','USA'),
('aldi_us','ALDI','USA'),
('amazon_us_same_day','Amazon Same Day (US)','USA'),
('kroger_us','Kroger','USA'),
('target_us','Target','USA'),
('safeway_us','Safeway','USA'),
('albertsons_us','Albertsons','USA'),
('heb_us','H-E-B','USA'),
('giant_eagle_us','Giant Eagle','USA'),
('meijer_us','Meijer','USA'),
('sams_club_us','Sam''s Club','USA'),
('shoprite_us','ShopRite','USA'),
('trader_joes_us','Trader Joe''s','USA'),
('wegmans_us','Wegmans','USA'),
('whole_foods_market_us','Whole Foods Market','USA')
ON CONFLICT (id) DO NOTHING;

INSERT INTO retailer_alias(alias,retailer_id) VALUES
('Walmart','walmart_us'),('walmart','walmart_us'),('walmart.com','walmart_us'),('Walmart (US)','walmart_us'),
('ALDI','aldi_us'),('aldi','aldi_us'),('aldi.us','aldi_us'),('new_aldi','aldi_us'),
('amazon','amazon_us_same_day'),('amazon.com','amazon_us_same_day'),('Amazon (US)','amazon_us_same_day'),
('kroger','kroger_us'),('Kroger','kroger_us'),
('Target','target_us'),('Safeway','safeway_us'),('Albertsons','albertsons_us'),('H-E-B','heb_us'),
('Giant Eagle','giant_eagle_us'),('Meijer','meijer_us'),('Sam''s Club','sams_club_us'),
('ShopRite','shoprite_us'),('Trader Joe''s','trader_joes_us'),('Wegmans','wegmans_us'),
('Whole Foods Market','whole_foods_market_us')
ON CONFLICT (alias) DO UPDATE SET retailer_id=excluded.retailer_id;
