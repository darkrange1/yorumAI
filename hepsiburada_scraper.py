from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import json
import sys
import re
import os
from datetime import datetime
from urllib.parse import urlparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

MAX_REVIEWS_PER_REQUEST = 3000  
REQUEST_TIMEOUT = 420  
RATE_LIMIT_DELAY = 2  
MAX_RETRIES = 3  

class ScraperSecurityError(Exception):
    pass

def validate_url(url):
    if not url or not isinstance(url, str):
        raise ScraperSecurityError("Geçersiz URL formatı")
    
    url = url.strip()
    
    try:
        parsed = urlparse(url)
    except Exception:
        raise ScraperSecurityError("URL parse edilemedi")
    
    allowed_domains = ['hepsiburada.com', 'www.hepsiburada.com']
    if parsed.netloc not in allowed_domains:
        raise ScraperSecurityError(f"Sadece Hepsiburada URL'leri kabul edilir. Verilen: {parsed.netloc}")
    
    if parsed.scheme not in ['http', 'https']:
        raise ScraperSecurityError("Sadece HTTP/HTTPS protokolü desteklenir")
    
    dangerous_chars = ['<', '>', '"', "'", ';', '(', ')', '{', '}']
    if any(char in url for char in dangerous_chars):
        raise ScraperSecurityError("URL'de tehlikeli karakterler tespit edildi")
    
    logger.info(f"URL validasyonu başarılı: {url}")
    return url

def sanitize_filename(name):
    dangerous = ['..', '/', '\\', ':', '*', '?', '"', '<', '>', '|', '\n', '\r', '\0']
    for char in dangerous:
        name = name.replace(char, '_')
    
    safe_name = re.sub(r'[^\w\s-]', '_', name)
    safe_name = re.sub(r'_+', '_', safe_name)[:50].strip('_')
    
    return safe_name

def save_to_json(data, filename):
    try:
        safe_filename = sanitize_filename(filename)
        
        if not safe_filename.endswith('.json'):
            safe_filename += '.json'
        
        with open(safe_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        logger.info(f"Dosya kaydedildi: {safe_filename}")
        print(f"\n💾 DOSYA KAYDEDİLDİ: {safe_filename}")
        return safe_filename
    except Exception as e:
        logger.error(f"Dosya kaydetme hatası: {e}")
        print(f"❌ Kayıt hatası: {e}")
        return None

def run(url, max_reviews=None):
    start_time = datetime.now()
    driver = None
    
    try:
        url = validate_url(url)
        
        if max_reviews is None:
            max_reviews = MAX_REVIEWS_PER_REQUEST
        elif max_reviews > MAX_REVIEWS_PER_REQUEST:
            logger.warning(f"Max reviews {MAX_REVIEWS_PER_REQUEST} ile sınırlandırıldı")
            max_reviews = MAX_REVIEWS_PER_REQUEST
        
        print(f"🚀 Sistem Başlatılıyor (Headless + Stealth Mod - Güvenli)...")
        logger.info(f"Scraping başlatıldı: {url}")
        
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")  
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-software-rasterizer")
        
        remote_url = os.getenv("SELENIUM_REMOTE_URL", "http://chrome:4444/wd/hub")
        driver = webdriver.Remote(command_executor=remote_url, options=chrome_options)
        
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(30)
        
        print(f"🔗 Ana ürün sayfasına gidiliyor...")
        driver.get(url)
        time.sleep(RATE_LIMIT_DELAY)
        
        if (datetime.now() - start_time).seconds > REQUEST_TIMEOUT:
            raise ScraperSecurityError("İşlem zaman aşımına uğradı")
        
        url_sku_match = re.search(r'-p-([A-Z0-9]+)(?:-yorumlari)?', url)
        sku = url_sku_match.group(1) if url_sku_match else None
        
        if not sku:
            page_source = driver.page_source
            sku_match = re.search(r'"product_skus":\["([A-Z0-9]+)"\]', page_source)
            sku = sku_match.group(1) if sku_match else None
        
        if not sku or not re.match(r'^[A-Z0-9]+$', sku):
            raise ScraperSecurityError("Geçersiz SKU formatı")
        
        try:
            product_name = driver.find_element(By.TAG_NAME, "h1").text.strip()
            product_name = sanitize_filename(product_name)
        except:
            product_name = "Urun"

        print(f"✅ Ürün: {product_name}")
        print(f"🏷️  SKU: {sku}")
        logger.info(f"SKU bulundu: {sku}")
        
        print(f"📥 Yorumlar çekiliyor (max: {max_reviews})...")
        
        all_reviews = []
        offset = 0 
        page_size = 100
        
        base_api_url = "https://user-content-gw-hermes.hepsiburada.com/queryapi/v2/ApprovedUserContents"
        
        retry_count = 0
        
        while len(all_reviews) < max_reviews:
            if (datetime.now() - start_time).seconds > REQUEST_TIMEOUT:
                logger.warning("Zaman aşımı - mevcut yorumlar döndürülüyor")
                break
            
            api_url = f"{base_api_url}?sku={sku}&from={offset}&size={page_size}&includeSiblingVariantContents=true&includeSummary=true"
            
            try:
                driver.get(api_url)
                time.sleep(RATE_LIMIT_DELAY)  
                
                body = driver.find_element(By.TAG_NAME, "body")
                body_text = body.text
                data = json.loads(body_text)
                
                if not data:
                    logger.warning("Boş veri alındı")
                    break
                
                content_list = data.get('data', {}).get('approvedUserContent', {}).get('approvedUserContentList', [])
                
                if not content_list:
                    logger.info("Tüm yorumlar alındı")
                    break
                
                for item in content_list:
                    if len(all_reviews) >= max_reviews:
                        break
                    
                    review_obj = item.get("review", {})
                    review_content = review_obj.get("content", "") if isinstance(review_obj, dict) else review_obj
                    
                    if review_content and isinstance(review_content, str):
                        all_reviews.append({
                            "content": review_content[:5000],  
                            "date": item.get("createdAt", "")
                        })
                
                print(f"   -> Blok: {offset}-{offset+page_size} | +{len(content_list)} yorum | Toplam: {len(all_reviews)}")
                
                if len(content_list) < page_size:
                    logger.info("Son paket alındı")
                    break
                
                offset += page_size
                retry_count = 0  
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse hatası: {e}")
                retry_count += 1
                if retry_count >= MAX_RETRIES:
                    logger.error("Maksimum deneme sayısına ulaşıldı")
                    break
                time.sleep(RATE_LIMIT_DELAY * retry_count)
            except Exception as e:
                logger.error(f"İstek hatası: {e}")
                retry_count += 1
                if retry_count >= MAX_RETRIES:
                    break
                time.sleep(RATE_LIMIT_DELAY * retry_count)
        
        final_data = {
            "product_name": product_name,
            "sku": sku,
            "total_reviews": len(all_reviews),
            "scraped_at": datetime.now().isoformat(),
            "reviews": all_reviews
        }
        
        if os.getenv("SCRAPER_SAVE_JSON", "false").lower() == "true":
            save_to_json(final_data, product_name)
        
        elapsed = (datetime.now() - start_time).seconds
        logger.info(f"Scraping tamamlandı. Süre: {elapsed}s, Yorum: {len(all_reviews)}")
        print(f"\n✅ Tamamlandı! {len(all_reviews)} yorum çekildi ({elapsed} saniye)")
        
        return final_data
        
    except ScraperSecurityError as e:
        logger.error(f"Güvenlik hatası: {e}")
        print(f"🛡️ GÜVENLİK HATASI: {e}")
        return None
    except Exception as e:
        logger.error(f"Beklenmeyen hata: {e}", exc_info=True)
        print(f"❌ HATA: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        url = input("🔗 Hepsiburada ürün linkini girin: ")
        if not url.strip():
            print("❌ Link girilmedi, çıkılıyor.")
            sys.exit(1)
    else:
        url = sys.argv[1]
    
    try:
        result = run(url)
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("Kullanıcı tarafından iptal edildi")
        print("\n⚠️ İşlem iptal edildi")
        sys.exit(130)
