create table if not exists public.rss_articles (
  id bigint generated always as identity primary key,
  feed_title text,
  feed_url text not null,
  item_guid text,
  article_url text not null,
  title text,
  author text,
  published_at timestamptz,
  summary text,
  content_text text,
  content_html text,
  source_domain text,
  lang text,
  extracted_via text,        -- 'rss_embedded' | 'trafilatura' | 'playwright+trafilatura' | 'firecrawl'
  rss_raw jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create unique index if not exists rss_articles_article_url_key
  on public.rss_articles(article_url);

create unique index if not exists rss_articles_guid_key
  on public.rss_articles(item_guid)
  where item_guid is not null;
