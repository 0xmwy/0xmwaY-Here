def test_lbank_public():

    urls = [
        "https://lbkperp.lbank.com/cfd/openApi/v1/pub/getTime",
        "https://www.lbank.com"
    ]

    results = []

    for url in urls:

        try:

            r = requests.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json,text/plain,*/*",
                    "Accept-Language": "en-US,en;q=0.9"
                },
                timeout=15
            )

            results.append({
                "url": url,
                "http_status": r.status_code,
                "content_type": r.headers.get(
                    "content-type"
                ),
                "server": r.headers.get(
                    "server"
                ),
                "response_preview": r.text[:500]
            })

        except Exception as e:

            results.append({
                "url": url,
                "error": str(e)
            })

    return results
