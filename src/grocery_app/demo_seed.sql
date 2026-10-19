--
-- PostgreSQL database dump
--

\restrict ybgGxhs9wcBbanAIyG9ExSXhcJLydM5wJgZ3PqoLwgw1s0Jw7OgxpHq70S1d4wi

-- Dumped from database version 16.15 (Homebrew)
-- Dumped by pg_dump version 16.15 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.checks (
    id integer NOT NULL,
    receipt_id integer NOT NULL,
    "position" integer NOT NULL,
    raw_name character varying NOT NULL,
    app_product_id character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: checks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.checks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: checks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.checks_id_seq OWNED BY public.checks.id;


--
-- Name: corrections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.corrections (
    id integer NOT NULL,
    receipt_id integer,
    "position" integer NOT NULL,
    store character varying,
    raw_name character varying NOT NULL,
    machine_how character varying NOT NULL,
    machine_product_id character varying NOT NULL,
    shopper_product_id character varying,
    corrected_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: corrections_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.corrections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: corrections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.corrections_id_seq OWNED BY public.corrections.id;


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id uuid NOT NULL,
    status character varying NOT NULL,
    image_sha256 character varying(64) NOT NULL,
    original_filename character varying,
    receipt_id integer,
    model character varying,
    prompt_version character varying,
    request_id character varying,
    usage jsonb,
    cost_usd numeric(10,5),
    error character varying,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    already_added boolean DEFAULT false NOT NULL,
    turned_away character varying,
    user_id integer,
    dev_seen_at timestamp with time zone,
    shared_at timestamp with time zone
);


--
-- Name: line_guesses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.line_guesses (
    id integer NOT NULL,
    receipt_id integer NOT NULL,
    "position" integer NOT NULL,
    name character varying,
    category character varying,
    reading character varying
);


--
-- Name: line_guesses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.line_guesses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: line_guesses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.line_guesses_id_seq OWNED BY public.line_guesses.id;


--
-- Name: line_resolutions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.line_resolutions (
    id integer NOT NULL,
    receipt_id integer NOT NULL,
    "position" integer NOT NULL,
    raw_name character varying NOT NULL,
    product_id character varying,
    confirmed_by character varying,
    confirmed_at date,
    basis character varying,
    shopper_words character varying,
    memory_before jsonb,
    disagrees_with character varying,
    rejected character varying
);


--
-- Name: line_resolutions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.line_resolutions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: line_resolutions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.line_resolutions_id_seq OWNED BY public.line_resolutions.id;


--
-- Name: model_calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_calls (
    id integer NOT NULL,
    at timestamp with time zone DEFAULT now() NOT NULL,
    purpose character varying NOT NULL,
    job_id uuid,
    model character varying NOT NULL,
    input_tokens integer NOT NULL,
    output_tokens integer NOT NULL,
    searches integer NOT NULL,
    cost_usd numeric(10,5)
);


--
-- Name: model_calls_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.model_calls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: model_calls_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.model_calls_id_seq OWNED BY public.model_calls.id;


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    id character varying NOT NULL,
    label character varying,
    name character varying NOT NULL,
    brand character varying,
    size jsonb,
    category character varying,
    is_organic boolean,
    eans character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    open_questions character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    provenance jsonb,
    nutrition jsonb,
    enrichment jsonb,
    extra jsonb,
    details character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    picture jsonb,
    picture_checked_at timestamp with time zone
);


--
-- Name: questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.questions (
    id integer NOT NULL,
    receipt_id integer NOT NULL,
    "position" integer NOT NULL,
    raw_name character varying NOT NULL,
    proposal jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    answered_at timestamp with time zone
);


--
-- Name: questions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.questions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: questions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.questions_id_seq OWNED BY public.questions.id;


--
-- Name: receipt_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.receipt_lines (
    id integer NOT NULL,
    receipt_id integer NOT NULL,
    "position" integer NOT NULL,
    type character varying NOT NULL,
    raw_name character varying NOT NULL,
    qty integer NOT NULL,
    unit_gross numeric(10,2),
    gross numeric(10,2),
    discount numeric(10,2),
    net numeric(10,2) NOT NULL,
    tax_class character varying(4),
    sold_by_weight boolean,
    weight_kg numeric(8,3),
    unit_price numeric(10,2),
    unit_price_basis character varying
);


--
-- Name: receipt_lines_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.receipt_lines_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: receipt_lines_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.receipt_lines_id_seq OWNED BY public.receipt_lines.id;


--
-- Name: receipts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.receipts (
    id integer NOT NULL,
    source_image character varying NOT NULL,
    transcribed_by character varying NOT NULL,
    store character varying,
    store_location character varying,
    date date,
    "time" character varying(8),
    currency character varying(3),
    printed_total numeric(10,2),
    printed_savings numeric(10,2),
    tax_buckets jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    image_sha256 character varying(64),
    user_id integer,
    seen_at timestamp with time zone
);


--
-- Name: receipts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.receipts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: receipts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.receipts_id_seq OWNED BY public.receipts.id;


--
-- Name: resolutions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resolutions (
    id integer NOT NULL,
    store character varying NOT NULL,
    raw_name character varying NOT NULL,
    line_type character varying NOT NULL,
    product_id character varying,
    product_ids character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    status character varying,
    confirmed_by character varying,
    confirmed_at date,
    source character varying
);


--
-- Name: resolutions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resolutions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resolutions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resolutions_id_seq OWNED BY public.resolutions.id;


--
-- Name: sign_ins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sign_ins (
    id integer NOT NULL,
    token_sha256 character varying(64) NOT NULL,
    user_id integer,
    email character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: sign_ins_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sign_ins_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sign_ins_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sign_ins_id_seq OWNED BY public.sign_ins.id;


--
-- Name: store_listings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.store_listings (
    id integer NOT NULL,
    store character varying NOT NULL,
    article_number character varying NOT NULL,
    product_id character varying NOT NULL,
    url character varying,
    prices jsonb DEFAULT '[]'::jsonb NOT NULL
);


--
-- Name: store_listings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.store_listings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: store_listings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.store_listings_id_seq OWNED BY public.store_listings.id;


--
-- Name: uncounted_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.uncounted_lines (
    id integer NOT NULL,
    receipt_id integer NOT NULL,
    "position" integer NOT NULL,
    raw_name character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: uncounted_lines_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.uncounted_lines_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: uncounted_lines_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.uncounted_lines_id_seq OWNED BY public.uncounted_lines.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    name character varying NOT NULL,
    token_sha256 character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    email character varying
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: checks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checks ALTER COLUMN id SET DEFAULT nextval('public.checks_id_seq'::regclass);


--
-- Name: corrections id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.corrections ALTER COLUMN id SET DEFAULT nextval('public.corrections_id_seq'::regclass);


--
-- Name: line_guesses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.line_guesses ALTER COLUMN id SET DEFAULT nextval('public.line_guesses_id_seq'::regclass);


--
-- Name: line_resolutions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.line_resolutions ALTER COLUMN id SET DEFAULT nextval('public.line_resolutions_id_seq'::regclass);


--
-- Name: model_calls id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_calls ALTER COLUMN id SET DEFAULT nextval('public.model_calls_id_seq'::regclass);


--
-- Name: questions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questions ALTER COLUMN id SET DEFAULT nextval('public.questions_id_seq'::regclass);


--
-- Name: receipt_lines id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipt_lines ALTER COLUMN id SET DEFAULT nextval('public.receipt_lines_id_seq'::regclass);


--
-- Name: receipts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipts ALTER COLUMN id SET DEFAULT nextval('public.receipts_id_seq'::regclass);


--
-- Name: resolutions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resolutions ALTER COLUMN id SET DEFAULT nextval('public.resolutions_id_seq'::regclass);


--
-- Name: sign_ins id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sign_ins ALTER COLUMN id SET DEFAULT nextval('public.sign_ins_id_seq'::regclass);


--
-- Name: store_listings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_listings ALTER COLUMN id SET DEFAULT nextval('public.store_listings_id_seq'::regclass);


--
-- Name: uncounted_lines id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.uncounted_lines ALTER COLUMN id SET DEFAULT nextval('public.uncounted_lines_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.alembic_version VALUES ('0022');


--
-- Data for Name: checks; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.checks VALUES (43, 58, 3, 'Mutti Passata 500g', 'p-0028', '2026-10-19 16:24:40.757102+02');
INSERT INTO public.checks VALUES (44, 60, 4, 'Dr.Oetker Ristorante Salame', 'p-0023', '2026-10-19 16:25:05.574262+02');
INSERT INTO public.checks VALUES (45, 60, 5, 'Gerolsteiner Naturell 1,5L', 'p-0021', '2026-10-19 16:25:05.574262+02');


--
-- Data for Name: corrections; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: jobs; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.jobs VALUES ('83f949ac-140b-4051-9387-30e070df24ce', 'done', 'e653cb99a9d488b6ea9e53f9cb8b4ca86c55c51f0b4ebae8aa5f604eb2232089', '2026-06-28-aldi-sued.jpg', 23, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:11:53.511318+02', '2026-10-19 16:11:53.513505+02', '2026-10-19 16:11:53.547614+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('52aded1d-64d9-4f2f-95b1-49d84318f623', 'done', '6cb0e11112b1e587bafd02c7533830f6c7ac1fde6c8ff6ed3b0fc0c2a9aeaf50', '2026-04-21-aldi-sued.jpg', 1, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 15:23:25.98347+02', '2026-10-19 15:23:25.986008+02', '2026-10-19 15:29:33.206484+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('55475128-6eff-413b-add2-60750142029b', 'done', 'a54314bce3a836bd3c2630fe51d27f2dc82d60e09da77d73770bad22839c6afe', '2026-05-15-globus.jpg', 9, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:05:41.160164+02', '2026-10-19 16:05:41.161801+02', '2026-10-19 16:07:45.348004+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('923a4df5-138c-48ff-9fd7-fc4410622324', 'done', '8cedcc92bbd8833038e0a52dcbf6d96dbbb7dd70566d92861dae377e6487e134', '2026-04-25-globus.jpg', 2, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 15:29:33.257411+02', '2026-10-19 15:29:33.265046+02', '2026-10-19 15:39:44.584769+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('352c94f4-7a0a-4a2a-83ad-f07cedafd2da', 'done', 'fad289010aa857c85780ec4620164cbd8b54e3d303bb3d444687833365988e91', '2026-06-06-globus.jpg', 15, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:09:36.915228+02', '2026-10-19 16:09:36.918232+02', '2026-10-19 16:09:45.587889+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('111de58f-15e8-4e28-aaa7-fd99e99a01a8', 'done', 'e569df420572c3b9a7639556f7548136fe8e75be0de1b4447ff77694ba975cc4', '2026-07-08-aldi-sued.jpg', 26, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:13:34.703008+02', '2026-10-19 16:13:34.705926+02', '2026-10-19 16:13:34.729771+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('f60cd09c-c06c-4483-b698-64caaa396870', 'done', '816bfd963804fe3f1a2834bfebc9f7ce8fda8c27d1dddd56928e04ec33aaf1e2', '2026-04-27-lidl.jpg', 3, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 15:39:44.628968+02', '2026-10-19 15:39:44.632231+02', '2026-10-19 15:49:38.375039+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('0d6d0f56-722e-48c8-9aa6-8178c1778735', 'done', '8e38aee51f28d68dfdf6761613d110aaff68dba95c9949b199d0400b32044b22', '2026-05-18-lidl.jpg', 10, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:07:45.365772+02', '2026-10-19 16:07:45.367693+02', '2026-10-19 16:08:27.427915+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('bbc5fd2c-54be-4113-b3d9-0025d15286c8', 'done', '9195c8da4a9395ac264d8b208449688813b430ccc19b9585a7d420e7bdd6ddb6', '2026-06-19-aldi-sued.jpg', 20, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:11:20.788215+02', '2026-10-19 16:11:20.791313+02', '2026-10-19 16:11:20.810555+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('fd37936e-1210-4e9e-8587-2d7dfce458ea', 'done', '9e65726090c6a3c9493f8a72be04d1a6be35b8e8e14e40992cc44758fc9db668', '2026-05-01-aldi-sued.jpg', 4, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 15:49:38.410482+02', '2026-10-19 15:49:38.412615+02', '2026-10-19 15:58:16.579445+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'done', 'adf053d1f6f9bd40e582b84f129d5ad3130ffc1a7f152ddde24ba4192ce4386b', '2026-06-07-kaufland.jpg', 16, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:09:45.608636+02', '2026-10-19 16:09:45.610259+02', '2026-10-19 16:10:39.399424+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('b8b24b0c-5369-49b9-986b-1dce51467cda', 'done', 'f22105fcf4d29355ab2eb00e3ff676e6d4d5fd5efd6b81e1ec1daf318f3a0809', '2026-05-20-aldi-sued.jpg', 11, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:08:27.440502+02', '2026-10-19 16:08:27.44245+02', '2026-10-19 16:08:42.352174+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('342118bc-992e-46df-86bb-488874ae474d', 'done', 'd45efb4f3124b7f617cc24bd4db303838518b9bb27dc6f6139c7cd38fa373c80', '2026-05-02-globus.jpg', 5, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 15:58:16.616213+02', '2026-10-19 15:58:16.618857+02', '2026-10-19 16:03:53.490276+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('90681ab5-5bce-44e6-b575-8c7b17425320', 'done', '40f9c8caf3389b70fa8301b3c8b1f35e8f2e4a32ef5733914b22d90db54f7d15', '2026-05-02-kaufland.jpg', 6, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:03:53.51998+02', '2026-10-19 16:03:53.52356+02', '2026-10-19 16:05:21.686343+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('1591e41b-fcae-4f50-a047-a0fd8299830d', 'done', 'd7b7d7bad23c5a8cf906aaf6d00d48de736c9fe5581ec4a2e84fbf68d5f1a6da', '2026-07-18-aldi-sued.jpg', 30, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:14:23.124262+02', '2026-10-19 16:14:23.12624+02', '2026-10-19 16:14:23.153414+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('6de940aa-103a-4962-a903-80198c052297', 'done', 'f500632601a483972bbb897eca648ff781de9836f0e1f98014a8cc5561cb3bcb', '2026-05-23-globus.jpg', 12, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:08:42.369904+02', '2026-10-19 16:08:42.371312+02', '2026-10-19 16:09:20.031458+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('996c3201-303d-4ed4-9f4b-8d5ff21a10cd', 'done', '0380c1bc1106c0c8312339c47bad7533fdffa486d5897d620f8b49be280b6653', '2026-05-08-globus.jpg', 7, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:05:21.719733+02', '2026-10-19 16:05:21.722464+02', '2026-10-19 16:05:30.865796+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('a452bd0b-2f77-41c9-9ad7-6ceee13203ef', 'done', '51574ff5a8804373a8564395d920a053358238171f5a175b60a87fc993c14e67', '2026-06-30-lidl.jpg', 24, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:11:53.563263+02', '2026-10-19 16:11:53.565364+02', '2026-10-19 16:12:48.553362+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('89e54083-10f0-41a5-9e5b-3a33b7070100', 'done', '793165c805d15cdf11a9effb721ec57447f3e8b7fa136619e18bf9cb72260119', '2026-06-08-aldi-sued.jpg', 17, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:10:39.41129+02', '2026-10-19 16:10:39.412702+02', '2026-10-19 16:10:39.437066+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('f0939090-a23d-43cf-98fa-19c5c24c60e3', 'done', '1814e7999de88bb0166db6275020faff9ed0e10bb26cd186d5b2832892cef814', '2026-05-11-aldi-sued.jpg', 8, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:05:30.895194+02', '2026-10-19 16:05:30.898282+02', '2026-10-19 16:05:41.141978+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('1a76dc3a-1949-408d-b2d6-073e8d092f1a', 'done', '7e76b37d2f01b663b74cf786ade1654439537555b1c1931e985f214fc36402dc', '2026-05-30-aldi-sued.jpg', 13, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:09:20.053998+02', '2026-10-19 16:09:20.055935+02', '2026-10-19 16:09:20.075992+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('dc4d8a80-ed9a-4ac7-814b-9f78fb295318', 'done', '2a00d175916ac5985d9be7bbceee3feefd3a4fe1b6d97235dd5bada6b7429a72', '2026-06-19-globus.jpg', 21, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:11:20.829837+02', '2026-10-19 16:11:20.831574+02', '2026-10-19 16:11:27.313801+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('129cf811-509d-44cf-b504-bf288ab25c89', 'done', '1b9fa6d2b12a767cc1099b20df1381377c80b143095939d77253c1ce3586b44c', '2026-05-30-globus.jpg', 14, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:09:20.091087+02', '2026-10-19 16:09:20.092597+02', '2026-10-19 16:09:36.878679+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('f8aa8d99-4b05-4e34-8d4a-1f5c37ce4702', 'done', '4c611496c21e6dea6d4d7d6102253e442ed05d080d16280a49b9f5504b32a4f2', '2026-06-08-lidl.jpg', 18, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:10:39.449775+02', '2026-10-19 16:10:39.451145+02', '2026-10-19 16:10:39.471155+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('b40de9a7-3cca-425f-837a-9270208c2929', 'done', 'fe2b114ac08e6eb537ee7b6612a652c236156b5705d364f1e27d702f29b34834', '2026-06-26-globus.jpg', 22, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:11:27.333302+02', '2026-10-19 16:11:27.335553+02', '2026-10-19 16:11:53.49213+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('e7e08cc7-afe8-4eb3-b583-8e4822f5c873', 'done', '6cd2df957b63ab967e3b9bd9c3997a400e571d7b8c4e95fc534e2729b64bbafa', '2026-06-12-globus.jpg', 19, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:10:39.492517+02', '2026-10-19 16:10:39.493985+02', '2026-10-19 16:11:20.773773+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('5c5b1a64-1964-483a-8be5-a290944bc9e5', 'done', 'dd62d9e1c00c7abcebc6b2e8dd1ef094fc894a05b50ffdb98c330586318c3c00', '2026-07-09-globus.jpg', 27, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:13:34.745535+02', '2026-10-19 16:13:34.747602+02', '2026-10-19 16:13:40.534967+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('5cd5ff93-673a-4ed7-8c6d-77743ca56a58', 'done', 'e5601394441cdd5506a48b7a4f7b5793aa079bda30dc900635c3fe87d16e9e2e', '2026-07-02-globus.jpg', 25, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:12:48.589291+02', '2026-10-19 16:12:48.592273+02', '2026-10-19 16:13:34.686583+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('7cc3999d-8598-43ab-ab68-05592e5af63a', 'done', '146cf13e51baa1794f33220e808fe4e094cfa27e5abf84dafc46c1e2cc7c8f90', '2026-07-17-globus.jpg', 29, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:14:23.072237+02', '2026-10-19 16:14:23.074602+02', '2026-10-19 16:14:23.109593+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('2c9ba5de-80fb-4731-a1e1-8dc27b74bd3e', 'done', '3eb0e26793811675f7dae6cfe60b5352ebb785b38c7b5aaa737f937a4b5543e5', '2026-07-31-globus.jpg', 34, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:16:22.290076+02', '2026-10-19 16:16:22.291611+02', '2026-10-19 16:16:22.322066+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('b0c9a042-32b2-4d5f-b6c8-0ef6317541de', 'done', 'd9b9b5eb50d29780f72500935d81b15a8d010b78317bfa5073a70768115ba686', '2026-07-12-kaufland.jpg', 28, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:13:40.550406+02', '2026-10-19 16:13:40.552669+02', '2026-10-19 16:14:23.049666+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('f7a033b7-2185-4d86-9a4c-6f69d13a01ef', 'done', '50d8e91a713e66db46d28315100b25f1365e080462b2a34349885f86543ea821', '2026-07-24-globus.jpg', 32, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:16:22.171617+02', '2026-10-19 16:16:22.173932+02', '2026-10-19 16:16:22.20895+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('22936693-c82b-45fd-b875-0ced3ef3be14', 'done', '01e4916f10d96f7be7acaabcc3b4a827341448e0103f9292ab9051397385070c', '2026-07-20-lidl.jpg', 31, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:14:23.171543+02', '2026-10-19 16:14:23.173416+02', '2026-10-19 16:16:22.145994+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('d4d0a967-9bb0-4a07-b8ce-66ff30d36140', 'done', '63c1569006c87ca4cf837c2527daf1b911a6521e8e2f5c63a9e92a9881d411b1', '2026-07-29-aldi-sued.jpg', 33, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:16:22.225379+02', '2026-10-19 16:16:22.227632+02', '2026-10-19 16:16:22.270384+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('fe830023-373a-4f60-87f3-174158c49d23', 'done', '6afc035f6b5ad2f56792947893754c3bccdb2755d186a59fbeb8e470d0d5089a', '2026-08-06-globus.jpg', 35, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:16:22.339241+02', '2026-10-19 16:16:22.341438+02', '2026-10-19 16:16:22.374973+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('a23f76a4-8cab-417d-b259-11b602782e56', 'done', 'b10fa8c82fbfeb4a3f2a8edd19117d39d899cf66451fe55037f9de4ed0ede909', '2026-08-08-aldi-sued.jpg', 36, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:16:22.388568+02', '2026-10-19 16:16:22.390441+02', '2026-10-19 16:16:22.414175+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('8bbcb349-f2cc-4155-a04b-d96516483698', 'done', 'e674bb2ff3f346163f52a673225cca1701c8fa4ebe8be2bc1e34140505182360', '2026-08-10-lidl.jpg', 37, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:16:22.42631+02', '2026-10-19 16:16:22.427824+02', '2026-10-19 16:16:22.455334+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('33efe068-e8b7-4cef-ac3a-357d4cc78a8b', 'done', '6b0152f44453ec106835c9122deff2802fdbabbb9a1494dd3f9f77543e6eb4d8', '2026-08-12-globus.jpg', 38, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:16:22.474441+02', '2026-10-19 16:16:22.47618+02', '2026-10-19 16:17:12.736508+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('6c0a092a-33f3-47d3-a12d-16c26c385d92', 'done', '0ded519ef24e3eea72b76ace3a3b0f2748b5bbbfc180cbae479d83b81468702d', '2026-08-15-kaufland.jpg', 39, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:17:12.751641+02', '2026-10-19 16:17:12.753576+02', '2026-10-19 16:17:21.82764+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('81189e37-9403-42a0-8951-482353eb0eb1', 'done', '67be5337e0bfaf17a0671dd1f424eb2824e338e8a8d1225288615a2851108948', '2026-08-18-aldi-sued.jpg', 40, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:17:21.847409+02', '2026-10-19 16:17:21.849289+02', '2026-10-19 16:17:31.006419+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('388f8053-b9c5-441b-af86-aa42e10b8775', 'done', '5b1a80cfd98da0ddbb27476f83ab12cc075eed1ebda624b3e713ddfae0fce425', '2026-09-16-aldi-sued.jpg', 48, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:22:38.923351+02', '2026-10-19 16:22:38.925418+02', '2026-10-19 16:22:48.284517+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('be03b57f-3cd3-47c8-8f28-c3a313a9cb49', 'done', 'e09dc8c20727c513955da742b529f48f71d920f43f848e1f07a13e1ad4f68596', '2026-08-20-globus.jpg', 41, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:17:31.028032+02', '2026-10-19 16:17:31.031439+02', '2026-10-19 16:17:31.127142+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('dfd8aa04-a2a0-4fb4-9aef-8e29461968a4', 'done', 'cb56d44b36d5f5d4800cfcbc796a74611a1d52100825892eeca2cc7ee9f2e4a2', '2026-10-02-globus.jpg', 54, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:23:09.803577+02', '2026-10-19 16:23:09.805686+02', '2026-10-19 16:23:45.428132+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('48ddca8b-97dc-4cbd-ad1b-66ddf5982f2b', 'done', '4b11afe29e62d69559f9f0522d602047f75ec4bbc6e02a7544d833910661b8be', '2026-08-27-globus.jpg', 42, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:17:31.144095+02', '2026-10-19 16:17:31.146101+02', '2026-10-19 16:17:57.563439+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('e125f29f-91c5-4177-b3cb-ffa1920dba92', 'done', '9c9965f9c34cbcbd69f90d52214b0e38726bdde45c7f98e9567f167f41accd64', '2026-09-17-globus.jpg', 49, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:22:48.303369+02', '2026-10-19 16:22:48.305685+02', '2026-10-19 16:22:55.386662+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('36cffe8a-7676-45de-8c94-80353b6a6d58', 'done', 'e86aebb5e83311bac36b13445737defd8eeef754e2931a30bbc93b30cce2aaa7', '2026-10-18-aldi-sued.jpg', 59, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:24:40.79616+02', '2026-10-19 16:24:40.7986+02', '2026-10-19 16:24:40.840258+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('93de8b29-9ec5-4952-8f6c-197cbf488bf0', 'done', 'a6617aaf9af69ac2be5c67ffeff2d3f131229e667ea699d055fe9f36de518180', '2026-08-28-aldi-sued.jpg', 43, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:17:57.576368+02', '2026-10-19 16:17:57.578014+02', '2026-10-19 16:18:14.390764+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('8d8ab30d-0ac4-49dc-b3ac-aaf388e3bbca', 'done', 'e00d40a0d4912a1640d64c4763d961a0d15de8d122329784579b7a37c7881301', '2026-10-07-aldi-sued.jpg', 55, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:23:45.453571+02', '2026-10-19 16:23:45.456946+02', '2026-10-19 16:23:55.040333+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('04776bab-bc79-44c0-999a-4e644a76e5cb', 'done', 'd9e4c3798b204b3fdfa3068a09603ddac2572e9083b7237401ef64bdba5a995b', '2026-09-19-kaufland.jpg', 50, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:22:55.398646+02', '2026-10-19 16:22:55.400265+02', '2026-10-19 16:22:55.433481+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('414f76b1-1c6b-41e0-bb01-5bda14cde7e9', 'done', '2ea4e0cbedc796354d27816378153ca7d63e73c87e6c73f6b9c98e127e419909', '2026-08-31-lidl.jpg', 44, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:18:14.403606+02', '2026-10-19 16:18:14.405964+02', '2026-10-19 16:18:14.435022+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('d93ec000-88b3-4f9b-8740-18fc1f8a463b', 'done', '31422f7165515d916bf624ee457b5b5af06005effc11ae2dd54e95747e44df54', '2026-09-03-globus.jpg', 45, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:18:14.45564+02', '2026-10-19 16:18:14.457303+02', '2026-10-19 16:18:50.373619+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('aee4a44b-51aa-4e21-a462-7f242a91674f', 'done', '6be738b3f2c37079071e0d1a909be9a551e90b93c66a84358e05b7028c09755a', '2026-09-21-lidl.jpg', 51, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:22:55.44534+02', '2026-10-19 16:22:55.446904+02', '2026-10-19 16:22:55.475989+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('2a5d356e-c427-412b-887c-24e7e4559128', 'done', '88a6d09409d7f8156632dfc75d47c34bd006de8382ca97c28a2da3f9818197d1', '2026-09-07-aldi-sued.jpg', 46, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:18:50.395592+02', '2026-10-19 16:18:50.398585+02', '2026-10-19 16:22:38.857749+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('5bbc7385-48da-4c7c-a8ab-70173aac642e', 'done', '6e24c8679b4b7a57ab0f3544e290029d641300c9cc6f2ee4530534428d51c57a', '2026-10-09-globus.jpg', 56, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:23:55.06224+02', '2026-10-19 16:23:55.065122+02', '2026-10-19 16:24:20.743532+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('0dd3828f-e5d5-4da7-b411-62713728bc54', 'done', 'aec3bf1f93c56ba8e85a2340fc9c4fcf533b48e89ead0467d517766bc366936f', '2026-09-11-globus.jpg', 47, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:22:38.876451+02', '2026-10-19 16:22:38.878558+02', '2026-10-19 16:22:38.909402+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('b72967fe-b7da-4504-a2ee-04f39f693cd1', 'done', 'e17c61556d0f8e66fa05e2b778b0a8c9bb3b734ab6d8be1e71700ba770dd157f', '2026-09-24-globus.jpg', 52, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:22:55.49134+02', '2026-10-19 16:22:55.492959+02', '2026-10-19 16:23:09.730901+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('faf598d7-0757-491d-a67d-07f989be606b', 'done', '268635a2ed0d2febdcb742b7d95f2d2a111e32e681dc17686992b30075351659', '2026-10-19-globus.jpg', 60, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:24:40.860616+02', '2026-10-19 16:24:40.86236+02', '2026-10-19 16:25:05.609881+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('e5d9f291-8e6a-453b-b9c1-0f1af3075c05', 'done', '2cd783ea529741102b3fa57b5c5b51101541e882f3128234615055cbf81ccea1', '2026-09-26-aldi-sued.jpg', 53, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:23:09.749221+02', '2026-10-19 16:23:09.750859+02', '2026-10-19 16:23:09.78117+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('69b9e0d4-f59e-4393-ae40-84181c51713a', 'done', 'b6ea40c3a5d4125a46c5e751b24ac3ff9ded12335add74a884569c8582ffb62e', '2026-10-11-lidl.jpg', 57, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:24:20.770534+02', '2026-10-19 16:24:20.773209+02', '2026-10-19 16:24:35.938073+02', false, NULL, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('94c7d4e3-e232-4ed8-bd39-824323067750', 'done', 'a82ae749a537238236e065e7c74f6ac632c428ab4fc9775679d9dfcc4186755b', '2026-10-15-globus.jpg', 58, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-19 16:24:35.959908+02', '2026-10-19 16:24:35.96258+02', '2026-10-19 16:24:40.77712+02', false, NULL, NULL, NULL, NULL);


--
-- Data for Name: line_guesses; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: line_resolutions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: model_calls; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.model_calls VALUES (1, '2026-10-19 15:23:45.035014+02', 'finding', '52aded1d-64d9-4f2f-95b1-49d84318f623', 'gemini-3.8-flash', 750, 314, 0, 0.00191);
INSERT INTO public.model_calls VALUES (2, '2026-10-19 15:24:06.133261+02', 'finding', '52aded1d-64d9-4f2f-95b1-49d84318f623', 'gemini-3.8-flash', 4401, 359, 0, 0.00511);
INSERT INTO public.model_calls VALUES (3, '2026-10-19 15:24:11.262049+02', 'finding', '52aded1d-64d9-4f2f-95b1-49d84318f623', 'gemini-3.8-flash', 4730, 408, 0, 0.00559);
INSERT INTO public.model_calls VALUES (4, '2026-10-19 15:24:15.554773+02', 'finding', '52aded1d-64d9-4f2f-95b1-49d84318f623', 'gemini-3.8-flash', 814, 250, 0, 0.00170);
INSERT INTO public.model_calls VALUES (5, '2026-10-19 15:24:19.543044+02', 'finding', '52aded1d-64d9-4f2f-95b1-49d84318f623', 'gemini-3.8-flash', 4441, 307, 0, 0.00493);
INSERT INTO public.model_calls VALUES (6, '2026-10-19 15:28:43.173792+02', 'finding', '52aded1d-64d9-4f2f-95b1-49d84318f623', 'gemini-3.8-flash', 4949, 262, 0, 0.00516);
INSERT INTO public.model_calls VALUES (7, '2026-10-19 15:29:12.885406+02', 'finding', '52aded1d-64d9-4f2f-95b1-49d84318f623', 'gemini-3.8-flash', 883, 2651, 0, 0.01166);
INSERT INTO public.model_calls VALUES (8, '2026-10-19 15:29:21.584883+02', 'finding', '52aded1d-64d9-4f2f-95b1-49d84318f623', 'gemini-3.8-flash', 4483, 772, 0, 0.00688);
INSERT INTO public.model_calls VALUES (9, '2026-10-19 15:29:33.143765+02', 'finding', '52aded1d-64d9-4f2f-95b1-49d84318f623', 'gemini-3.8-flash', 4803, 1113, 0, 0.00855);
INSERT INTO public.model_calls VALUES (10, '2026-10-19 15:29:45.397703+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 840, 239, 0, 0.00168);
INSERT INTO public.model_calls VALUES (11, '2026-10-19 15:30:29.036101+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4450, 4965, 0, 0.02415);
INSERT INTO public.model_calls VALUES (12, '2026-10-19 15:31:20.695912+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 339, 1214, 4, 0.06129);
INSERT INTO public.model_calls VALUES (13, '2026-10-19 15:31:38.237278+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 513, 1022, 0, 0.00464);
INSERT INTO public.model_calls VALUES (14, '2026-10-19 15:31:59.680808+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4789, 363, 0, 0.00545);
INSERT INTO public.model_calls VALUES (15, '2026-10-19 15:32:07.719038+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 756, 413, 0, 0.00233);
INSERT INTO public.model_calls VALUES (16, '2026-10-19 15:32:12.591521+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4370, 291, 0, 0.00481);
INSERT INTO public.model_calls VALUES (17, '2026-10-19 15:32:20.888105+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4760, 327, 0, 0.00528);
INSERT INTO public.model_calls VALUES (18, '2026-10-19 15:32:27.154349+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 840, 193, 0, 0.00149);
INSERT INTO public.model_calls VALUES (19, '2026-10-19 15:32:36.040209+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4431, 243, 0, 0.00466);
INSERT INTO public.model_calls VALUES (20, '2026-10-19 15:33:29.00553+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 343, 877, 6, 0.08790);
INSERT INTO public.model_calls VALUES (21, '2026-10-19 15:33:41.187231+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 510, 1146, 0, 0.00515);
INSERT INTO public.model_calls VALUES (22, '2026-10-19 15:33:52.205465+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4756, 298, 0, 0.00515);
INSERT INTO public.model_calls VALUES (23, '2026-10-19 15:34:05.862995+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 897, 343, 0, 0.00215);
INSERT INTO public.model_calls VALUES (24, '2026-10-19 15:34:13.772664+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4452, 454, 0, 0.00555);
INSERT INTO public.model_calls VALUES (25, '2026-10-19 15:34:23.481094+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4692, 625, 0, 0.00645);
INSERT INTO public.model_calls VALUES (26, '2026-10-19 15:34:27.583315+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 673, 145, 0, 0.00115);
INSERT INTO public.model_calls VALUES (27, '2026-10-19 15:34:37.214899+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4292, 320, 0, 0.00486);
INSERT INTO public.model_calls VALUES (28, '2026-10-19 15:38:37.040348+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 340, 1273, 6, 0.08953);
INSERT INTO public.model_calls VALUES (29, '2026-10-19 15:38:59.045208+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 593, 373, 0, 0.00203);
INSERT INTO public.model_calls VALUES (30, '2026-10-19 15:39:44.527991+02', 'finding', '923a4df5-138c-48ff-9fd7-fc4410622324', 'gemini-3.8-flash', 4710, 4240, 0, 0.02138);
INSERT INTO public.model_calls VALUES (31, '2026-10-19 15:39:47.382794+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 642, 182, 0, 0.00128);
INSERT INTO public.model_calls VALUES (32, '2026-10-19 15:39:53.61961+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4263, 660, 0, 0.00624);
INSERT INTO public.model_calls VALUES (33, '2026-10-19 15:40:08.724209+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 333, 1406, 3, 0.04807);
INSERT INTO public.model_calls VALUES (34, '2026-10-19 15:40:15.645457+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 539, 267, 0, 0.00155);
INSERT INTO public.model_calls VALUES (35, '2026-10-19 15:40:28.760778+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4602, 811, 0, 0.00714);
INSERT INTO public.model_calls VALUES (36, '2026-10-19 15:40:31.972436+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 630, 155, 0, 0.00116);
INSERT INTO public.model_calls VALUES (37, '2026-10-19 15:40:38.475351+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4261, 456, 0, 0.00540);
INSERT INTO public.model_calls VALUES (38, '2026-10-19 15:41:09.622983+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 334, 1852, 5, 0.07792);
INSERT INTO public.model_calls VALUES (39, '2026-10-19 15:41:15.677586+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 584, 786, 0, 0.00372);
INSERT INTO public.model_calls VALUES (40, '2026-10-19 15:41:23.955135+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4571, 519, 0, 0.00591);
INSERT INTO public.model_calls VALUES (41, '2026-10-19 15:41:26.913859+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 630, 172, 0, 0.00123);
INSERT INTO public.model_calls VALUES (42, '2026-10-19 15:41:36.436893+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4259, 369, 0, 0.00504);
INSERT INTO public.model_calls VALUES (43, '2026-10-19 15:46:33.130059+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 332, 1824, 24, 0.34380);
INSERT INTO public.model_calls VALUES (44, '2026-10-19 15:46:48.777842+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 446, 205, 0, 0.00121);
INSERT INTO public.model_calls VALUES (45, '2026-10-19 15:46:52.727747+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4754, 313, 0, 0.00521);
INSERT INTO public.model_calls VALUES (46, '2026-10-19 15:47:03.918639+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 632, 109, 0, 0.00097);
INSERT INTO public.model_calls VALUES (47, '2026-10-19 15:47:32.056211+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4268, 372, 0, 0.00506);
INSERT INTO public.model_calls VALUES (48, '2026-10-19 15:47:58.416085+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 338, 628, 3, 0.04487);
INSERT INTO public.model_calls VALUES (49, '2026-10-19 15:48:05.263685+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 445, 970, 0, 0.00437);
INSERT INTO public.model_calls VALUES (50, '2026-10-19 15:48:08.657514+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4525, 303, 0, 0.00498);
INSERT INTO public.model_calls VALUES (51, '2026-10-19 15:48:12.84249+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 634, 157, 0, 0.00117);
INSERT INTO public.model_calls VALUES (52, '2026-10-19 15:48:16.68462+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4264, 374, 0, 0.00506);
INSERT INTO public.model_calls VALUES (53, '2026-10-19 15:49:04.195538+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 334, 2576, 23, 0.33290);
INSERT INTO public.model_calls VALUES (54, '2026-10-19 15:49:22.381644+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 530, 257, 0, 0.00150);
INSERT INTO public.model_calls VALUES (55, '2026-10-19 15:49:38.340015+02', 'finding', 'f60cd09c-c06c-4483-b698-64caaa396870', 'gemini-3.8-flash', 4864, 423, 0, 0.00576);
INSERT INTO public.model_calls VALUES (56, '2026-10-19 15:51:24.127355+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 929, 287, 0, 0.00195);
INSERT INTO public.model_calls VALUES (57, '2026-10-19 15:52:29.46046+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 4518, 183, 0, 0.00448);
INSERT INTO public.model_calls VALUES (58, '2026-10-19 15:54:17.711192+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 329, 875, 9, 0.12988);
INSERT INTO public.model_calls VALUES (59, '2026-10-19 15:54:25.65851+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 506, 924, 0, 0.00423);
INSERT INTO public.model_calls VALUES (60, '2026-10-19 15:54:37.445326+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 4847, 222, 0, 0.00491);
INSERT INTO public.model_calls VALUES (61, '2026-10-19 15:54:57.031304+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 900, 254, 0, 0.00179);
INSERT INTO public.model_calls VALUES (62, '2026-10-19 15:55:31.13506+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 4481, 497, 0, 0.00575);
INSERT INTO public.model_calls VALUES (63, '2026-10-19 15:56:39.571418+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 344, 1286, 11, 0.15959);
INSERT INTO public.model_calls VALUES (64, '2026-10-19 15:56:43.885636+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 557, 259, 0, 0.00153);
INSERT INTO public.model_calls VALUES (65, '2026-10-19 15:56:49.624243+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 4924, 661, 0, 0.00679);
INSERT INTO public.model_calls VALUES (66, '2026-10-19 15:56:54.41802+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 960, 478, 0, 0.00276);
INSERT INTO public.model_calls VALUES (67, '2026-10-19 15:57:05.645283+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 4533, 1417, 0, 0.00958);
INSERT INTO public.model_calls VALUES (68, '2026-10-19 15:57:16.080985+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 4955, 1279, 0, 0.00936);
INSERT INTO public.model_calls VALUES (69, '2026-10-19 15:57:21.406121+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 912, 632, 0, 0.00336);
INSERT INTO public.model_calls VALUES (70, '2026-10-19 15:57:25.192425+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 4501, 396, 0, 0.00535);
INSERT INTO public.model_calls VALUES (71, '2026-10-19 15:57:29.623674+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 5136, 476, 0, 0.00620);
INSERT INTO public.model_calls VALUES (72, '2026-10-19 15:57:32.774976+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 892, 213, 0, 0.00161);
INSERT INTO public.model_calls VALUES (73, '2026-10-19 15:57:36.070571+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 4474, 358, 0, 0.00517);
INSERT INTO public.model_calls VALUES (74, '2026-10-19 15:58:06.899175+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 338, 1491, 21, 0.30043);
INSERT INTO public.model_calls VALUES (75, '2026-10-19 15:58:12.300515+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 486, 721, 0, 0.00338);
INSERT INTO public.model_calls VALUES (76, '2026-10-19 15:58:16.55198+02', 'finding', 'fd37936e-1210-4e9e-8587-2d7dfce458ea', 'gemini-3.8-flash', 4987, 358, 0, 0.00559);
INSERT INTO public.model_calls VALUES (87, '2026-10-19 16:01:46.410234+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 720, 217, 0, 0.00149);
INSERT INTO public.model_calls VALUES (88, '2026-10-19 16:01:51.80512+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 4371, 442, 0, 0.00543);
INSERT INTO public.model_calls VALUES (89, '2026-10-19 16:02:08.86768+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 4733, 2349, 0, 0.01359);
INSERT INTO public.model_calls VALUES (95, '2026-10-19 16:03:58.027251+02', 'finding', '90681ab5-5bce-44e6-b575-8c7b17425320', 'gemini-3.8-flash', 628, 131, 0, 0.00106);
INSERT INTO public.model_calls VALUES (96, '2026-10-19 16:04:02.474782+02', 'finding', '90681ab5-5bce-44e6-b575-8c7b17425320', 'gemini-3.8-flash', 4248, 391, 0, 0.00512);
INSERT INTO public.model_calls VALUES (97, '2026-10-19 16:04:04.112138+02', 'finding', '90681ab5-5bce-44e6-b575-8c7b17425320', 'gemini-3.8-flash', 625, 85, 0, 0.00087);
INSERT INTO public.model_calls VALUES (98, '2026-10-19 16:04:07.771964+02', 'finding', '90681ab5-5bce-44e6-b575-8c7b17425320', 'gemini-3.8-flash', 4251, 306, 0, 0.00477);
INSERT INTO public.model_calls VALUES (99, '2026-10-19 16:04:11.458154+02', 'finding', '90681ab5-5bce-44e6-b575-8c7b17425320', 'gemini-3.8-flash', 650, 180, 0, 0.00128);
INSERT INTO public.model_calls VALUES (100, '2026-10-19 16:04:31.341931+02', 'finding', '90681ab5-5bce-44e6-b575-8c7b17425320', 'gemini-3.8-flash', 4261, 2781, 0, 0.01499);
INSERT INTO public.model_calls VALUES (101, '2026-10-19 16:04:33.391901+02', 'finding', '90681ab5-5bce-44e6-b575-8c7b17425320', 'gemini-3.8-flash', 630, 87, 0, 0.00088);
INSERT INTO public.model_calls VALUES (102, '2026-10-19 16:04:54.044525+02', 'finding', '90681ab5-5bce-44e6-b575-8c7b17425320', 'gemini-3.8-flash', 4249, 2906, 0, 0.01549);
INSERT INTO public.model_calls VALUES (103, '2026-10-19 16:05:21.659141+02', 'finding', '90681ab5-5bce-44e6-b575-8c7b17425320', 'gemini-3.8-flash', 4751, 4097, 0, 0.02082);
INSERT INTO public.model_calls VALUES (104, '2026-10-19 16:05:25.516738+02', 'finding', '996c3201-303d-4ed4-9f4b-8d5ff21a10cd', 'gemini-3.8-flash', 925, 380, 0, 0.00233);
INSERT INTO public.model_calls VALUES (105, '2026-10-19 16:05:30.842436+02', 'finding', '996c3201-303d-4ed4-9f4b-8d5ff21a10cd', 'gemini-3.8-flash', 4502, 484, 0, 0.00571);
INSERT INTO public.model_calls VALUES (106, '2026-10-19 16:05:34.284761+02', 'finding', 'f0939090-a23d-43cf-98fa-19c5c24c60e3', 'gemini-3.8-flash', 911, 276, 0, 0.00189);
INSERT INTO public.model_calls VALUES (107, '2026-10-19 16:05:41.127683+02', 'finding', 'f0939090-a23d-43cf-98fa-19c5c24c60e3', 'gemini-3.8-flash', 4474, 697, 0, 0.00657);
INSERT INTO public.model_calls VALUES (108, '2026-10-19 16:05:43.686873+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 741, 187, 0, 0.00138);
INSERT INTO public.model_calls VALUES (109, '2026-10-19 16:05:47.27204+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 4400, 361, 0, 0.00512);
INSERT INTO public.model_calls VALUES (110, '2026-10-19 16:05:51.848561+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 670, 421, 0, 0.00229);
INSERT INTO public.model_calls VALUES (111, '2026-10-19 16:05:56.314095+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 4349, 335, 0, 0.00497);
INSERT INTO public.model_calls VALUES (112, '2026-10-19 16:06:01.170464+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 803, 501, 0, 0.00273);
INSERT INTO public.model_calls VALUES (77, '2026-10-19 15:58:20.124978+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 892, 317, 0, 0.00204);
INSERT INTO public.model_calls VALUES (78, '2026-10-19 15:58:26.031643+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 4497, 347, 0, 0.00514);
INSERT INTO public.model_calls VALUES (79, '2026-10-19 16:00:27.880558+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 329, 1252, 10, 0.14544);
INSERT INTO public.model_calls VALUES (80, '2026-10-19 16:00:34.437431+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 381, 833, 0, 0.00375);
INSERT INTO public.model_calls VALUES (81, '2026-10-19 16:00:40.989319+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 4784, 595, 0, 0.00640);
INSERT INTO public.model_calls VALUES (82, '2026-10-19 16:00:47.139479+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 666, 328, 0, 0.00190);
INSERT INTO public.model_calls VALUES (83, '2026-10-19 16:00:53.283411+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 4335, 535, 0, 0.00578);
INSERT INTO public.model_calls VALUES (84, '2026-10-19 16:01:24.755755+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 333, 1736, 16, 0.23144);
INSERT INTO public.model_calls VALUES (85, '2026-10-19 16:01:31.475838+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 596, 871, 0, 0.00408);
INSERT INTO public.model_calls VALUES (86, '2026-10-19 16:01:37.207068+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 4881, 519, 0, 0.00617);
INSERT INTO public.model_calls VALUES (90, '2026-10-19 16:02:13.053782+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 681, 206, 0, 0.00141);
INSERT INTO public.model_calls VALUES (91, '2026-10-19 16:02:17.262884+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 4345, 453, 0, 0.00545);
INSERT INTO public.model_calls VALUES (92, '2026-10-19 16:03:38.549451+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 343, 2396, 34, 0.48617);
INSERT INTO public.model_calls VALUES (93, '2026-10-19 16:03:49.462711+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 448, 717, 0, 0.00333);
INSERT INTO public.model_calls VALUES (94, '2026-10-19 16:03:53.465327+02', 'finding', '342118bc-992e-46df-86bb-488874ae474d', 'gemini-3.8-flash', 5044, 411, 0, 0.00586);
INSERT INTO public.model_calls VALUES (113, '2026-10-19 16:06:31.234044+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 4469, 3559, 0, 0.01837);
INSERT INTO public.model_calls VALUES (114, '2026-10-19 16:06:59.318852+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 4850, 3044, 0, 0.01656);
INSERT INTO public.model_calls VALUES (115, '2026-10-19 16:07:01.463144+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 664, 117, 0, 0.00103);
INSERT INTO public.model_calls VALUES (116, '2026-10-19 16:07:33.3606+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 4339, 4899, 0, 0.02379);
INSERT INTO public.model_calls VALUES (117, '2026-10-19 16:07:41.483167+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 946, 288, 0, 0.00197);
INSERT INTO public.model_calls VALUES (118, '2026-10-19 16:07:45.330458+02', 'finding', '55475128-6eff-413b-add2-60750142029b', 'gemini-3.8-flash', 4571, 261, 0, 0.00485);
INSERT INTO public.model_calls VALUES (119, '2026-10-19 16:07:49.338332+02', 'finding', '0d6d0f56-722e-48c8-9aa6-8178c1778735', 'gemini-3.8-flash', 630, 134, 0, 0.00107);
INSERT INTO public.model_calls VALUES (120, '2026-10-19 16:08:27.412063+02', 'finding', '0d6d0f56-722e-48c8-9aa6-8178c1778735', 'gemini-3.8-flash', 4253, 5896, 0, 0.02783);
INSERT INTO public.model_calls VALUES (121, '2026-10-19 16:08:32.802321+02', 'finding', 'b8b24b0c-5369-49b9-986b-1dce51467cda', 'gemini-3.8-flash', 4445, 506, 0, 0.00575);
INSERT INTO public.model_calls VALUES (122, '2026-10-19 16:08:42.331784+02', 'finding', 'b8b24b0c-5369-49b9-986b-1dce51467cda', 'gemini-3.8-flash', 4947, 403, 0, 0.00574);
INSERT INTO public.model_calls VALUES (123, '2026-10-19 16:08:44.687677+02', 'finding', '6de940aa-103a-4962-a903-80198c052297', 'gemini-3.8-flash', 741, 152, 0, 0.00124);
INSERT INTO public.model_calls VALUES (124, '2026-10-19 16:08:48.760378+02', 'finding', '6de940aa-103a-4962-a903-80198c052297', 'gemini-3.8-flash', 4400, 392, 0, 0.00525);
INSERT INTO public.model_calls VALUES (125, '2026-10-19 16:08:52.898507+02', 'finding', '6de940aa-103a-4962-a903-80198c052297', 'gemini-3.8-flash', 4728, 287, 0, 0.00508);
INSERT INTO public.model_calls VALUES (126, '2026-10-19 16:09:05.774321+02', 'finding', '6de940aa-103a-4962-a903-80198c052297', 'gemini-3.8-flash', 695, 952, 0, 0.00450);
INSERT INTO public.model_calls VALUES (127, '2026-10-19 16:09:08.725131+02', 'finding', '6de940aa-103a-4962-a903-80198c052297', 'gemini-3.8-flash', 4366, 337, 0, 0.00499);
INSERT INTO public.model_calls VALUES (128, '2026-10-19 16:09:12.943693+02', 'finding', '6de940aa-103a-4962-a903-80198c052297', 'gemini-3.8-flash', 928, 385, 0, 0.00235);
INSERT INTO public.model_calls VALUES (129, '2026-10-19 16:09:16.306966+02', 'finding', '6de940aa-103a-4962-a903-80198c052297', 'gemini-3.8-flash', 4537, 363, 0, 0.00524);
INSERT INTO public.model_calls VALUES (130, '2026-10-19 16:09:20.008954+02', 'finding', '6de940aa-103a-4962-a903-80198c052297', 'gemini-3.8-flash', 4946, 557, 0, 0.00638);
INSERT INTO public.model_calls VALUES (131, '2026-10-19 16:09:23.700093+02', 'finding', '129cf811-509d-44cf-b504-bf288ab25c89', 'gemini-3.8-flash', 673, 434, 0, 0.00235);
INSERT INTO public.model_calls VALUES (132, '2026-10-19 16:09:36.86259+02', 'finding', '129cf811-509d-44cf-b504-bf288ab25c89', 'gemini-3.8-flash', 4313, 612, 0, 0.00608);
INSERT INTO public.model_calls VALUES (133, '2026-10-19 16:09:41.553314+02', 'finding', '352c94f4-7a0a-4a2a-83ad-f07cedafd2da', 'gemini-3.8-flash', 949, 281, 0, 0.00194);
INSERT INTO public.model_calls VALUES (134, '2026-10-19 16:09:45.573635+02', 'finding', '352c94f4-7a0a-4a2a-83ad-f07cedafd2da', 'gemini-3.8-flash', 4550, 269, 0, 0.00486);
INSERT INTO public.model_calls VALUES (135, '2026-10-19 16:09:49.518401+02', 'finding', 'ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'gemini-3.8-flash', 631, 132, 0, 0.00107);
INSERT INTO public.model_calls VALUES (136, '2026-10-19 16:09:52.901157+02', 'finding', 'ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'gemini-3.8-flash', 4256, 331, 0, 0.00488);
INSERT INTO public.model_calls VALUES (137, '2026-10-19 16:09:57.074401+02', 'finding', 'ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'gemini-3.8-flash', 4581, 289, 0, 0.00497);
INSERT INTO public.model_calls VALUES (138, '2026-10-19 16:10:05.065731+02', 'finding', 'ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'gemini-3.8-flash', 629, 87, 0, 0.00088);
INSERT INTO public.model_calls VALUES (139, '2026-10-19 16:10:10.192407+02', 'finding', 'ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'gemini-3.8-flash', 4254, 356, 0, 0.00498);
INSERT INTO public.model_calls VALUES (140, '2026-10-19 16:10:11.965556+02', 'finding', 'ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'gemini-3.8-flash', 630, 78, 0, 0.00084);
INSERT INTO public.model_calls VALUES (141, '2026-10-19 16:10:14.852665+02', 'finding', 'ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'gemini-3.8-flash', 4261, 291, 0, 0.00472);
INSERT INTO public.model_calls VALUES (142, '2026-10-19 16:10:17.657314+02', 'finding', 'ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'gemini-3.8-flash', 627, 141, 0, 0.00110);
INSERT INTO public.model_calls VALUES (143, '2026-10-19 16:10:39.379967+02', 'finding', 'ccc22ecd-a6a7-40bf-814c-dbbca5d3e1de', 'gemini-3.8-flash', 4254, 639, 0, 0.00615);
INSERT INTO public.model_calls VALUES (144, '2026-10-19 16:11:04.464796+02', 'finding', 'e7e08cc7-afe8-4eb3-b583-8e4822f5c873', 'gemini-3.8-flash', 669, 291, 0, 0.00175);
INSERT INTO public.model_calls VALUES (145, '2026-10-19 16:11:08.481125+02', 'finding', 'e7e08cc7-afe8-4eb3-b583-8e4822f5c873', 'gemini-3.8-flash', 4339, 348, 0, 0.00502);
INSERT INTO public.model_calls VALUES (146, '2026-10-19 16:11:15.964052+02', 'finding', 'e7e08cc7-afe8-4eb3-b583-8e4822f5c873', 'gemini-3.8-flash', 4861, 813, 0, 0.00736);
INSERT INTO public.model_calls VALUES (147, '2026-10-19 16:11:20.750827+02', 'finding', 'e7e08cc7-afe8-4eb3-b583-8e4822f5c873', 'gemini-3.8-flash', 4558, 301, 0, 0.00500);
INSERT INTO public.model_calls VALUES (148, '2026-10-19 16:11:27.294634+02', 'finding', 'dc4d8a80-ed9a-4ac7-814b-9f78fb295318', 'gemini-3.8-flash', 4576, 289, 0, 0.00497);
INSERT INTO public.model_calls VALUES (149, '2026-10-19 16:11:30.889485+02', 'finding', 'b40de9a7-3cca-425f-837a-9270208c2929', 'gemini-3.8-flash', 4371, 266, 0, 0.00470);
INSERT INTO public.model_calls VALUES (150, '2026-10-19 16:11:45.236782+02', 'finding', 'b40de9a7-3cca-425f-837a-9270208c2929', 'gemini-3.8-flash', 933, 305, 0, 0.00203);
INSERT INTO public.model_calls VALUES (151, '2026-10-19 16:11:48.679688+02', 'finding', 'b40de9a7-3cca-425f-837a-9270208c2929', 'gemini-3.8-flash', 4552, 351, 0, 0.00520);
INSERT INTO public.model_calls VALUES (152, '2026-10-19 16:11:53.472465+02', 'finding', 'b40de9a7-3cca-425f-837a-9270208c2929', 'gemini-3.8-flash', 5208, 404, 0, 0.00596);
INSERT INTO public.model_calls VALUES (153, '2026-10-19 16:11:58.630205+02', 'finding', 'a452bd0b-2f77-41c9-9ad7-6ceee13203ef', 'gemini-3.8-flash', 631, 137, 0, 0.00109);
INSERT INTO public.model_calls VALUES (154, '2026-10-19 16:12:48.520221+02', 'finding', 'a452bd0b-2f77-41c9-9ad7-6ceee13203ef', 'gemini-3.8-flash', 4213, 7467, 0, 0.03428);
INSERT INTO public.model_calls VALUES (155, '2026-10-19 16:12:52.83982+02', 'finding', '5cd5ff93-673a-4ed7-8c6d-77743ca56a58', 'gemini-3.8-flash', 4405, 330, 0, 0.00500);
INSERT INTO public.model_calls VALUES (156, '2026-10-19 16:12:55.150723+02', 'finding', '5cd5ff93-673a-4ed7-8c6d-77743ca56a58', 'gemini-3.8-flash', 665, 137, 0, 0.00111);
INSERT INTO public.model_calls VALUES (157, '2026-10-19 16:13:24.225165+02', 'finding', '5cd5ff93-673a-4ed7-8c6d-77743ca56a58', 'gemini-3.8-flash', 4370, 2003, 0, 0.01187);
INSERT INTO public.model_calls VALUES (158, '2026-10-19 16:13:34.597377+02', 'finding', '5cd5ff93-673a-4ed7-8c6d-77743ca56a58', 'gemini-3.8-flash', 4598, 254, 0, 0.00484);
INSERT INTO public.model_calls VALUES (159, '2026-10-19 16:13:40.521494+02', 'finding', '5c5b1a64-1964-483a-8be5-a290944bc9e5', 'gemini-3.8-flash', 4545, 286, 0, 0.00493);
INSERT INTO public.model_calls VALUES (160, '2026-10-19 16:13:43.903129+02', 'finding', 'b0c9a042-32b2-4d5f-b6c8-0ef6317541de', 'gemini-3.8-flash', 631, 135, 0, 0.00108);
INSERT INTO public.model_calls VALUES (161, '2026-10-19 16:13:51.782598+02', 'finding', 'b0c9a042-32b2-4d5f-b6c8-0ef6317541de', 'gemini-3.8-flash', 4246, 334, 0, 0.00488);
INSERT INTO public.model_calls VALUES (162, '2026-10-19 16:13:54.328973+02', 'finding', 'b0c9a042-32b2-4d5f-b6c8-0ef6317541de', 'gemini-3.8-flash', 627, 114, 0, 0.00099);
INSERT INTO public.model_calls VALUES (163, '2026-10-19 16:13:59.904338+02', 'finding', 'b0c9a042-32b2-4d5f-b6c8-0ef6317541de', 'gemini-3.8-flash', 4251, 274, 0, 0.00464);
INSERT INTO public.model_calls VALUES (164, '2026-10-19 16:14:14.729186+02', 'finding', 'b0c9a042-32b2-4d5f-b6c8-0ef6317541de', 'gemini-3.8-flash', 4257, 1965, 0, 0.01162);
INSERT INTO public.model_calls VALUES (165, '2026-10-19 16:14:19.327196+02', 'finding', 'b0c9a042-32b2-4d5f-b6c8-0ef6317541de', 'gemini-3.8-flash', 634, 160, 0, 0.00118);
INSERT INTO public.model_calls VALUES (166, '2026-10-19 16:14:23.033024+02', 'finding', 'b0c9a042-32b2-4d5f-b6c8-0ef6317541de', 'gemini-3.8-flash', 4261, 357, 0, 0.00499);
INSERT INTO public.model_calls VALUES (167, '2026-10-19 16:14:26.108936+02', 'finding', '22936693-c82b-45fd-b875-0ced3ef3be14', 'gemini-3.8-flash', 627, 115, 0, 0.00099);
INSERT INTO public.model_calls VALUES (168, '2026-10-19 16:14:33.25324+02', 'finding', '22936693-c82b-45fd-b875-0ced3ef3be14', 'gemini-3.8-flash', 4269, 196, 0, 0.00433);
INSERT INTO public.model_calls VALUES (169, '2026-10-19 16:16:22.12475+02', 'finding', '22936693-c82b-45fd-b875-0ced3ef3be14', 'gemini-3.8-flash', 4255, 12300, 0, 0.05425);
INSERT INTO public.model_calls VALUES (170, '2026-10-19 16:16:27.435786+02', 'finding', '33efe068-e8b7-4cef-ac3a-357d4cc78a8b', 'gemini-3.8-flash', 4366, 359, 0, 0.00508);
INSERT INTO public.model_calls VALUES (171, '2026-10-19 16:17:12.715958+02', 'finding', '33efe068-e8b7-4cef-ac3a-357d4cc78a8b', 'gemini-3.8-flash', 4331, 5650, 0, 0.02688);
INSERT INTO public.model_calls VALUES (172, '2026-10-19 16:17:17.28517+02', 'finding', '6c0a092a-33f3-47d3-a12d-16c26c385d92', 'gemini-3.8-flash', 4233, 324, 0, 0.00483);
INSERT INTO public.model_calls VALUES (173, '2026-10-19 16:17:21.800863+02', 'finding', '6c0a092a-33f3-47d3-a12d-16c26c385d92', 'gemini-3.8-flash', 4243, 337, 0, 0.00489);
INSERT INTO public.model_calls VALUES (174, '2026-10-19 16:17:26.380694+02', 'finding', '81189e37-9403-42a0-8951-482353eb0eb1', 'gemini-3.8-flash', 893, 360, 0, 0.00222);
INSERT INTO public.model_calls VALUES (175, '2026-10-19 16:17:30.983892+02', 'finding', '81189e37-9403-42a0-8951-482353eb0eb1', 'gemini-3.8-flash', 4451, 420, 0, 0.00540);
INSERT INTO public.model_calls VALUES (176, '2026-10-19 16:17:36.303698+02', 'finding', '48ddca8b-97dc-4cbd-ad1b-66ddf5982f2b', 'gemini-3.8-flash', 4348, 343, 0, 0.00500);
INSERT INTO public.model_calls VALUES (177, '2026-10-19 16:17:57.54361+02', 'finding', '48ddca8b-97dc-4cbd-ad1b-66ddf5982f2b', 'gemini-3.8-flash', 4313, 3492, 0, 0.01796);
INSERT INTO public.model_calls VALUES (178, '2026-10-19 16:18:14.315006+02', 'finding', '93de8b29-9ec5-4952-8f6c-197cbf488bf0', 'gemini-3.8-flash', 4432, 464, 0, 0.00557);
INSERT INTO public.model_calls VALUES (179, '2026-10-19 16:18:50.349955+02', 'finding', 'd93ec000-88b3-4f9b-8740-18fc1f8a463b', 'gemini-3.8-flash', 4403, 380, 0, 0.00520);
INSERT INTO public.model_calls VALUES (180, '2026-10-19 16:20:13.33683+02', 'finding', '2a5d356e-c427-412b-887c-24e7e4559128', 'gemini-3.8-flash', 934, 236, 0, 0.00174);
INSERT INTO public.model_calls VALUES (181, '2026-10-19 16:22:38.837135+02', 'finding', '2a5d356e-c427-412b-887c-24e7e4559128', 'gemini-3.8-flash', 4498, 688, 0, 0.00655);
INSERT INTO public.model_calls VALUES (182, '2026-10-19 16:22:48.26046+02', 'finding', '388f8053-b9c5-441b-af86-aa42e10b8775', 'gemini-3.8-flash', 4486, 960, 0, 0.00766);
INSERT INTO public.model_calls VALUES (183, '2026-10-19 16:22:55.372755+02', 'finding', 'e125f29f-91c5-4177-b3cb-ffa1920dba92', 'gemini-3.8-flash', 4343, 631, 0, 0.00619);
INSERT INTO public.model_calls VALUES (184, '2026-10-19 16:23:04.022051+02', 'finding', 'b72967fe-b7da-4504-a2ee-04f39f693cd1', 'gemini-3.8-flash', 830, 521, 0, 0.00283);
INSERT INTO public.model_calls VALUES (185, '2026-10-19 16:23:09.711288+02', 'finding', 'b72967fe-b7da-4504-a2ee-04f39f693cd1', 'gemini-3.8-flash', 4435, 520, 0, 0.00580);
INSERT INTO public.model_calls VALUES (186, '2026-10-19 16:23:18.498853+02', 'finding', 'dfd8aa04-a2a0-4fb4-9aef-8e29461968a4', 'gemini-3.8-flash', 847, 714, 0, 0.00364);
INSERT INTO public.model_calls VALUES (187, '2026-10-19 16:23:25.271876+02', 'finding', 'dfd8aa04-a2a0-4fb4-9aef-8e29461968a4', 'gemini-3.8-flash', 4498, 565, 0, 0.00604);
INSERT INTO public.model_calls VALUES (188, '2026-10-19 16:23:31.421892+02', 'finding', 'dfd8aa04-a2a0-4fb4-9aef-8e29461968a4', 'gemini-3.8-flash', 632, 143, 0, 0.00111);
INSERT INTO public.model_calls VALUES (189, '2026-10-19 16:23:35.204442+02', 'finding', 'dfd8aa04-a2a0-4fb4-9aef-8e29461968a4', 'gemini-3.8-flash', 4318, 302, 0, 0.00481);
INSERT INTO public.model_calls VALUES (190, '2026-10-19 16:23:45.378603+02', 'finding', 'dfd8aa04-a2a0-4fb4-9aef-8e29461968a4', 'gemini-3.8-flash', 4475, 848, 0, 0.00719);
INSERT INTO public.model_calls VALUES (191, '2026-10-19 16:23:55.023126+02', 'finding', '8d8ab30d-0ac4-49dc-b3ac-aaf388e3bbca', 'gemini-3.8-flash', 4466, 920, 0, 0.00748);
INSERT INTO public.model_calls VALUES (192, '2026-10-19 16:24:10.015659+02', 'finding', '5bbc7385-48da-4c7c-a8ab-70173aac642e', 'gemini-3.8-flash', 4519, 1945, 0, 0.01175);
INSERT INTO public.model_calls VALUES (193, '2026-10-19 16:24:13.930112+02', 'finding', '5bbc7385-48da-4c7c-a8ab-70173aac642e', 'gemini-3.8-flash', 4346, 317, 0, 0.00489);
INSERT INTO public.model_calls VALUES (194, '2026-10-19 16:24:20.716723+02', 'finding', '5bbc7385-48da-4c7c-a8ab-70173aac642e', 'gemini-3.8-flash', 4503, 695, 0, 0.00658);
INSERT INTO public.model_calls VALUES (195, '2026-10-19 16:24:23.384467+02', 'finding', '69b9e0d4-f59e-4393-ae40-84181c51713a', 'gemini-3.8-flash', 606, 137, 0, 0.00107);
INSERT INTO public.model_calls VALUES (196, '2026-10-19 16:24:32.563519+02', 'finding', '69b9e0d4-f59e-4393-ae40-84181c51713a', 'gemini-3.8-flash', 4249, 1028, 0, 0.00775);
INSERT INTO public.model_calls VALUES (197, '2026-10-19 16:24:35.914356+02', 'finding', '69b9e0d4-f59e-4393-ae40-84181c51713a', 'gemini-3.8-flash', 4251, 247, 0, 0.00453);
INSERT INTO public.model_calls VALUES (198, '2026-10-19 16:24:40.753128+02', 'finding', '94c7d4e3-e232-4ed8-bd39-824323067750', 'gemini-3.8-flash', 4448, 491, 0, 0.00569);
INSERT INTO public.model_calls VALUES (199, '2026-10-19 16:24:53.530987+02', 'finding', 'faf598d7-0757-491d-a67d-07f989be606b', 'gemini-3.8-flash', 4483, 1624, 0, 0.01040);
INSERT INTO public.model_calls VALUES (200, '2026-10-19 16:24:59.465936+02', 'finding', 'faf598d7-0757-491d-a67d-07f989be606b', 'gemini-3.8-flash', 4310, 288, 0, 0.00474);
INSERT INTO public.model_calls VALUES (201, '2026-10-19 16:25:05.565551+02', 'finding', 'faf598d7-0757-491d-a67d-07f989be606b', 'gemini-3.8-flash', 4460, 515, 0, 0.00580);
INSERT INTO public.model_calls VALUES (202, '2026-10-19 16:25:47.086358+02', 'pictures', NULL, 'gemini-3.8-flash', 54, 2086, 12, 0.17665);
INSERT INTO public.model_calls VALUES (203, '2026-10-19 16:26:27.1027+02', 'pictures', NULL, 'gemini-3.8-flash', 55, 2042, 12, 0.17647);
INSERT INTO public.model_calls VALUES (204, '2026-10-19 16:28:26.116936+02', 'pictures', NULL, 'gemini-3.8-flash', 58, 2351, 18, 0.26175);
INSERT INTO public.model_calls VALUES (205, '2026-10-19 16:28:45.340905+02', 'pictures', NULL, 'gemini-3.8-flash', 55, 1124, 2, 0.03268);
INSERT INTO public.model_calls VALUES (206, '2026-10-19 16:28:59.252576+02', 'pictures', NULL, 'gemini-3.8-flash', 60, 999, 2, 0.03217);
INSERT INTO public.model_calls VALUES (207, '2026-10-19 16:30:15.385821+02', 'pictures', NULL, 'gemini-3.8-flash', 55, 1624, 28, 0.39874);
INSERT INTO public.model_calls VALUES (208, '2026-10-19 16:32:59.955009+02', 'pictures', NULL, 'gemini-3.8-flash', 61, 2846, 34, 0.48779);
INSERT INTO public.model_calls VALUES (209, '2026-10-19 16:34:10.818583+02', 'pictures', NULL, 'gemini-3.8-flash', 56, 2653, 20, 0.29099);
INSERT INTO public.model_calls VALUES (210, '2026-10-19 16:34:35.603988+02', 'pictures', NULL, 'gemini-3.8-flash', 61, 740, 5, 0.07310);
INSERT INTO public.model_calls VALUES (211, '2026-10-19 16:34:52.19055+02', 'pictures', NULL, 'gemini-3.8-flash', 52, 695, 3, 0.04491);
INSERT INTO public.model_calls VALUES (212, '2026-10-19 16:37:39.786043+02', 'pictures', NULL, 'gemini-3.8-flash', 53, 1734, 0, 0.00720);
INSERT INTO public.model_calls VALUES (213, '2026-10-19 16:39:10.143501+02', 'pictures', NULL, 'gemini-3.8-flash', 53, 2668, 30, 0.43105);
INSERT INTO public.model_calls VALUES (214, '2026-10-19 16:39:46.941169+02', 'pictures', NULL, 'gemini-3.8-flash', 51, 1295, 8, 0.11738);
INSERT INTO public.model_calls VALUES (215, '2026-10-19 16:40:24.382294+02', 'pictures', NULL, 'gemini-3.8-flash', 54, 1871, 19, 0.27376);
INSERT INTO public.model_calls VALUES (216, '2026-10-19 16:42:07.975346+02', 'pictures', NULL, 'gemini-3.8-flash', 59, 2708, 38, 0.54322);
INSERT INTO public.model_calls VALUES (217, '2026-10-19 16:43:22.880504+02', 'pictures', NULL, 'gemini-3.8-flash', 55, 2460, 20, 0.29019);
INSERT INTO public.model_calls VALUES (218, '2026-10-19 16:44:04.776195+02', 'pictures', NULL, 'gemini-3.8-flash', 54, 1858, 14, 0.20371);
INSERT INTO public.model_calls VALUES (219, '2026-10-19 16:49:41.119052+02', 'pictures', NULL, 'gemini-3.8-flash', 56, 3519, 35, 0.50456);
INSERT INTO public.model_calls VALUES (220, '2026-10-19 16:49:57.561951+02', 'pictures', NULL, 'gemini-3.8-flash', 56, 723, 2, 0.03103);
INSERT INTO public.model_calls VALUES (221, '2026-10-19 16:50:11.576465+02', 'pictures', NULL, 'gemini-3.8-flash', 55, 945, 4, 0.05994);
INSERT INTO public.model_calls VALUES (222, '2026-10-19 16:51:27.957402+02', 'pictures', NULL, 'gemini-3.8-flash', 53, 1535, 10, 0.14638);
INSERT INTO public.model_calls VALUES (223, '2026-10-19 16:52:04.53269+02', 'pictures', NULL, 'gemini-3.8-flash', 53, 1679, 6, 0.09097);
INSERT INTO public.model_calls VALUES (224, '2026-10-19 16:54:30.368831+02', 'finding', NULL, 'gemini-3.8-flash', 4255, 312, 0, 0.00480);
INSERT INTO public.model_calls VALUES (225, '2026-10-19 16:54:46.812433+02', 'finding', NULL, 'gemini-3.8-flash', 340, 1184, 4, 0.06116);
INSERT INTO public.model_calls VALUES (226, '2026-10-19 16:54:54.133179+02', 'finding', NULL, 'gemini-3.8-flash', 504, 931, 0, 0.00426);
INSERT INTO public.model_calls VALUES (227, '2026-10-19 16:54:58.019518+02', 'finding', NULL, 'gemini-3.8-flash', 4571, 319, 0, 0.00509);
INSERT INTO public.model_calls VALUES (228, '2026-10-19 16:55:15.381728+02', 'finding', NULL, 'gemini-3.8-flash', 342, 806, 3, 0.04561);
INSERT INTO public.model_calls VALUES (229, '2026-10-19 16:55:31.333874+02', 'finding', NULL, 'gemini-3.8-flash', 524, 906, 0, 0.00417);
INSERT INTO public.model_calls VALUES (230, '2026-10-19 16:55:46.073241+02', 'finding', NULL, 'gemini-3.8-flash', 4554, 1787, 0, 0.01113);
INSERT INTO public.model_calls VALUES (231, '2026-10-19 16:55:48.827925+02', 'finding', NULL, 'gemini-3.8-flash', 675, 112, 0, 0.00102);
INSERT INTO public.model_calls VALUES (232, '2026-10-19 16:57:25.404388+02', 'finding', NULL, 'gemini-3.8-flash', 4338, 11890, 0, 0.05263);
INSERT INTO public.model_calls VALUES (233, '2026-10-19 16:58:03.365958+02', 'finding', NULL, 'gemini-3.8-flash', 331, 948, 5, 0.07418);
INSERT INTO public.model_calls VALUES (234, '2026-10-19 16:58:16.243686+02', 'finding', NULL, 'gemini-3.8-flash', 527, 697, 0, 0.00331);
INSERT INTO public.model_calls VALUES (235, '2026-10-19 16:58:52.733228+02', 'finding', NULL, 'gemini-3.8-flash', 4637, 3842, 0, 0.01967);
INSERT INTO public.model_calls VALUES (236, '2026-10-19 16:59:07.334153+02', 'finding', NULL, 'gemini-3.8-flash', 4573, 284, 0, 0.00494);
INSERT INTO public.model_calls VALUES (237, '2026-10-19 17:03:06.808815+02', 'finding', NULL, 'gemini-3.8-flash', 339, 1653, 10, 0.14710);
INSERT INTO public.model_calls VALUES (238, '2026-10-19 17:03:13.981235+02', 'finding', NULL, 'gemini-3.8-flash', 488, 769, 0, 0.00357);
INSERT INTO public.model_calls VALUES (239, '2026-10-19 17:03:18.662789+02', 'finding', NULL, 'gemini-3.8-flash', 4952, 259, 0, 0.00515);
INSERT INTO public.model_calls VALUES (240, '2026-10-19 17:03:21.983258+02', 'finding', NULL, 'gemini-3.8-flash', 626, 123, 0, 0.00102);
INSERT INTO public.model_calls VALUES (241, '2026-10-19 17:04:00.536312+02', 'finding', NULL, 'gemini-3.8-flash', 4249, 4565, 0, 0.02234);
INSERT INTO public.model_calls VALUES (242, '2026-10-19 17:05:06.609509+02', 'finding', NULL, 'gemini-3.8-flash', 330, 1000, 5, 0.07440);
INSERT INTO public.model_calls VALUES (243, '2026-10-19 17:05:23.135848+02', 'finding', NULL, 'gemini-3.8-flash', 427, 513, 0, 0.00247);
INSERT INTO public.model_calls VALUES (244, '2026-10-19 17:05:56.063003+02', 'finding', NULL, 'gemini-3.8-flash', 4518, 4075, 0, 0.02054);
INSERT INTO public.model_calls VALUES (245, '2026-10-19 17:06:16.873191+02', 'finding', NULL, 'gemini-3.8-flash', 701, 2343, 0, 0.01024);
INSERT INTO public.model_calls VALUES (246, '2026-10-19 17:06:21.531078+02', 'finding', NULL, 'gemini-3.8-flash', 4364, 354, 0, 0.00506);
INSERT INTO public.model_calls VALUES (247, '2026-10-19 17:06:43.502259+02', 'finding', NULL, 'gemini-3.8-flash', 334, 1168, 6, 0.08909);
INSERT INTO public.model_calls VALUES (248, '2026-10-19 17:06:51.631985+02', 'finding', NULL, 'gemini-3.8-flash', 479, 1118, 0, 0.00501);
INSERT INTO public.model_calls VALUES (249, '2026-10-19 17:06:55.534817+02', 'finding', NULL, 'gemini-3.8-flash', 4682, 342, 0, 0.00527);
INSERT INTO public.model_calls VALUES (250, '2026-10-19 17:06:59.698247+02', 'finding', NULL, 'gemini-3.8-flash', 4256, 367, 0, 0.00503);
INSERT INTO public.model_calls VALUES (251, '2026-10-19 17:07:27.730092+02', 'finding', NULL, 'gemini-3.8-flash', 336, 1518, 5, 0.07654);
INSERT INTO public.model_calls VALUES (252, '2026-10-19 17:07:36.302688+02', 'finding', NULL, 'gemini-3.8-flash', 528, 1163, 0, 0.00523);
INSERT INTO public.model_calls VALUES (253, '2026-10-19 17:08:00.540187+02', 'finding', NULL, 'gemini-3.8-flash', 4614, 406, 0, 0.00548);
INSERT INTO public.model_calls VALUES (254, '2026-10-19 17:08:06.86364+02', 'finding', NULL, 'gemini-3.8-flash', 642, 86, 0, 0.00088);
INSERT INTO public.model_calls VALUES (255, '2026-10-19 17:08:13.650065+02', 'finding', NULL, 'gemini-3.8-flash', 4256, 733, 0, 0.00653);
INSERT INTO public.model_calls VALUES (256, '2026-10-19 17:09:47.00972+02', 'finding', NULL, 'gemini-3.8-flash', 334, 1540, 15, 0.21663);
INSERT INTO public.model_calls VALUES (257, '2026-10-19 17:09:55.788935+02', 'finding', NULL, 'gemini-3.8-flash', 520, 935, 0, 0.00429);
INSERT INTO public.model_calls VALUES (258, '2026-10-19 17:10:00.179596+02', 'finding', NULL, 'gemini-3.8-flash', 4758, 616, 0, 0.00647);
INSERT INTO public.model_calls VALUES (259, '2026-10-19 17:10:02.985678+02', 'finding', NULL, 'gemini-3.8-flash', 637, 152, 0, 0.00115);
INSERT INTO public.model_calls VALUES (260, '2026-10-19 17:10:06.5005+02', 'finding', NULL, 'gemini-3.8-flash', 4263, 332, 0, 0.00489);
INSERT INTO public.model_calls VALUES (261, '2026-10-19 17:10:35.889526+02', 'finding', NULL, 'gemini-3.8-flash', 342, 1351, 10, 0.14586);
INSERT INTO public.model_calls VALUES (262, '2026-10-19 17:10:42.955003+02', 'finding', NULL, 'gemini-3.8-flash', 546, 1408, 0, 0.00626);
INSERT INTO public.model_calls VALUES (263, '2026-10-19 17:10:48.625148+02', 'finding', NULL, 'gemini-3.8-flash', 4691, 327, 0, 0.00522);
INSERT INTO public.model_calls VALUES (267, '2026-10-19 17:11:23.826284+02', 'finding', NULL, 'gemini-3.8-flash', 897, 550, 0, 0.00301);
INSERT INTO public.model_calls VALUES (268, '2026-10-19 17:11:27.487578+02', 'finding', NULL, 'gemini-3.8-flash', 4448, 368, 0, 0.00519);
INSERT INTO public.model_calls VALUES (269, '2026-10-19 17:12:06.638573+02', 'finding', NULL, 'gemini-3.8-flash', 337, 1702, 15, 0.21730);
INSERT INTO public.model_calls VALUES (270, '2026-10-19 17:12:11.284599+02', 'finding', NULL, 'gemini-3.8-flash', 512, 919, 0, 0.00421);
INSERT INTO public.model_calls VALUES (271, '2026-10-19 17:12:15.337223+02', 'finding', NULL, 'gemini-3.8-flash', 4984, 488, 0, 0.00612);
INSERT INTO public.model_calls VALUES (277, '2026-10-19 17:13:06.896478+02', 'finding', NULL, 'gemini-3.8-flash', 837, 541, 0, 0.00292);
INSERT INTO public.model_calls VALUES (278, '2026-10-19 17:13:31.623771+02', 'finding', NULL, 'gemini-3.8-flash', 335, 1298, 11, 0.15963);
INSERT INTO public.model_calls VALUES (279, '2026-10-19 17:13:34.311616+02', 'finding', NULL, 'gemini-3.8-flash', 451, 228, 0, 0.00131);
INSERT INTO public.model_calls VALUES (280, '2026-10-19 17:13:41.605011+02', 'finding', NULL, 'gemini-3.8-flash', 4772, 1106, 0, 0.00850);
INSERT INTO public.model_calls VALUES (296, '2026-10-19 17:19:18.172501+02', 'pictures', NULL, 'gemini-3.8-flash', 54, 420, 4, 0.05778);
INSERT INTO public.model_calls VALUES (298, '2026-10-19 17:22:03.867279+02', 'pictures', NULL, 'gemini-3.8-flash', 54, 1968, 18, 0.26016);
INSERT INTO public.model_calls VALUES (264, '2026-10-19 17:11:08.829963+02', 'finding', NULL, 'gemini-3.8-flash', 333, 612, 10, 0.14280);
INSERT INTO public.model_calls VALUES (265, '2026-10-19 17:11:14.994714+02', 'finding', NULL, 'gemini-3.8-flash', 388, 783, 0, 0.00355);
INSERT INTO public.model_calls VALUES (266, '2026-10-19 17:11:18.228905+02', 'finding', NULL, 'gemini-3.8-flash', 4556, 236, 0, 0.00473);
INSERT INTO public.model_calls VALUES (272, '2026-10-19 17:12:18.842731+02', 'finding', NULL, 'gemini-3.8-flash', 925, 266, 0, 0.00186);
INSERT INTO public.model_calls VALUES (273, '2026-10-19 17:12:26.08319+02', 'finding', NULL, 'gemini-3.8-flash', 4494, 914, 0, 0.00748);
INSERT INTO public.model_calls VALUES (274, '2026-10-19 17:12:49.317688+02', 'finding', NULL, 'gemini-3.8-flash', 336, 1285, 16, 0.22958);
INSERT INTO public.model_calls VALUES (275, '2026-10-19 17:12:52.944225+02', 'finding', NULL, 'gemini-3.8-flash', 545, 288, 0, 0.00164);
INSERT INTO public.model_calls VALUES (276, '2026-10-19 17:13:00.548822+02', 'finding', NULL, 'gemini-3.8-flash', 5101, 866, 0, 0.00778);
INSERT INTO public.model_calls VALUES (281, '2026-10-19 17:13:46.397338+02', 'finding', NULL, 'gemini-3.8-flash', 848, 439, 0, 0.00251);
INSERT INTO public.model_calls VALUES (282, '2026-10-19 17:14:17.117343+02', 'finding', NULL, 'gemini-3.8-flash', 4500, 4006, 0, 0.02024);
INSERT INTO public.model_calls VALUES (283, '2026-10-19 17:14:41.700496+02', 'finding', NULL, 'gemini-3.8-flash', 343, 1573, 10, 0.14677);
INSERT INTO public.model_calls VALUES (284, '2026-10-19 17:14:43.695191+02', 'finding', NULL, 'gemini-3.8-flash', 549, 256, 0, 0.00151);
INSERT INTO public.model_calls VALUES (285, '2026-10-19 17:15:04.007969+02', 'finding', NULL, 'gemini-3.8-flash', 4899, 2757, 0, 0.01541);
INSERT INTO public.model_calls VALUES (286, '2026-10-19 17:15:10.246264+02', 'finding', NULL, 'gemini-3.8-flash', 645, 142, 0, 0.00112);
INSERT INTO public.model_calls VALUES (287, '2026-10-19 17:16:05.022558+02', 'finding', NULL, 'gemini-3.8-flash', 334, 1752, 23, 0.32950);
INSERT INTO public.model_calls VALUES (288, '2026-10-19 17:16:13.349797+02', 'finding', NULL, 'gemini-3.8-flash', 376, 724, 0, 0.00330);
INSERT INTO public.model_calls VALUES (289, '2026-10-19 17:16:35.149469+02', 'finding', NULL, 'gemini-3.8-flash', 4827, 261, 0, 0.00506);
INSERT INTO public.model_calls VALUES (290, '2026-10-19 17:16:43.449797+02', 'finding', NULL, 'gemini-3.8-flash', 611, 191, 0, 0.00129);
INSERT INTO public.model_calls VALUES (291, '2026-10-19 17:16:55.734331+02', 'finding', NULL, 'gemini-3.8-flash', 4249, 728, 0, 0.00651);
INSERT INTO public.model_calls VALUES (292, '2026-10-19 17:17:10.749768+02', 'finding', NULL, 'gemini-3.8-flash', 341, 1027, 4, 0.06052);
INSERT INTO public.model_calls VALUES (293, '2026-10-19 17:17:45.918244+02', 'finding', NULL, 'gemini-3.8-flash', 489, 593, 0, 0.00285);
INSERT INTO public.model_calls VALUES (294, '2026-10-19 17:18:08.234423+02', 'finding', NULL, 'gemini-3.8-flash', 4500, 2311, 0, 0.01325);
INSERT INTO public.model_calls VALUES (295, '2026-10-19 17:18:51.971883+02', 'pictures', NULL, 'gemini-3.8-flash', 56, 560, 7, 0.10036);
INSERT INTO public.model_calls VALUES (297, '2026-10-19 17:20:00.670393+02', 'pictures', NULL, 'gemini-3.8-flash', 58, 1463, 2, 0.03408);
INSERT INTO public.model_calls VALUES (299, '2026-10-19 17:22:34.076672+02', 'pictures', NULL, 'gemini-3.8-flash', 58, 858, 2, 0.03159);
INSERT INTO public.model_calls VALUES (300, '2026-10-19 17:42:30.076574+02', 'pictures', NULL, 'gemini-3.8-flash', 54, 2083, 13, 0.19064);


--
-- Data for Name: products; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.products VALUES ('p-0009', 'Vollmilch', 'Vollmilch', 'Milbona', '{"unit": null, "count": 1, "value": null}', 'milch', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{frisch}', NULL, '2026-10-19 16:26:30.502556+02');
INSERT INTO public.products VALUES ('p-0010', 'Kaffeebohnen', 'Kaffeebohnen', 'Barissimo', '{"unit": null, "count": 1, "value": null}', 'kaffee', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Crema}', NULL, '2026-10-19 16:28:33.121424+02');
INSERT INTO public.products VALUES ('p-0021', 'Mineralwasser still', 'Mineralwasser still', 'Gerolsteiner', '{"unit": null, "count": 1, "value": null}', 'wasser', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:28:48.41715+02');
INSERT INTO public.products VALUES ('p-0001', 'H-Milch', 'H-Milch', 'Milsani', '{"unit": null, "count": 1, "value": null}', 'milch', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{"1,5%"}', NULL, '2026-10-19 16:33:06.230736+02');
INSERT INTO public.products VALUES ('p-0002', 'Hähnchenbrustfilet', 'Hähnchenbrustfilet', NULL, '{"unit": null, "count": 1, "value": null}', 'gefluegel', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:33:06.239338+02');
INSERT INTO public.products VALUES ('p-0003', 'Joghurt', 'Joghurt', 'Milsani', '{"unit": null, "count": 1, "value": null}', 'joghurt', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Natur}', '{"file": "5d78f6fa13d591ee9ad8a2ad354c4df7f0a5c6f8966e6491fa31cd2df96e7713", "from": "supermarktcheck.de", "page": "https://www.supermarktcheck.de/product/90406-milsani-joghurt-", "source": "https://media.supermarktcheck.de/product/picture/large_792c6ed06b251d1f37a879dfa2694bb8.jpg"}', '2026-10-19 16:34:19.889736+02');
INSERT INTO public.products VALUES ('p-0005', 'Butter', 'Butter', 'Kerrygold', '{"unit": null, "count": 1, "value": null}', 'butter', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', '{"file": "bd0247f2adc86f408735b459e6926246d74244b8f4b19926f91e33a3c3235244", "from": "rewe.de", "page": "https://www.rewe.de/shop/p/kerrygold-original-irische-butter-250g/4529316", "source": "https://img.rewe-static.de/4529316/6648720_digital-image.png"}', '2026-10-19 16:34:55.511949+02');
INSERT INTO public.products VALUES ('p-0006', 'Rispentomaten', 'Rispentomaten', NULL, '{"unit": null, "count": 1, "value": null}', 'tomaten', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:34:55.517119+02');
INSERT INTO public.products VALUES ('p-0008', 'Cola', 'Cola', 'Coca-Cola', '{"unit": null, "count": 1, "value": null}', 'limonade', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:37:39.798495+02');
INSERT INTO public.products VALUES ('p-0011', 'Schmand', 'Schmand', 'Pilos', '{"unit": null, "count": 1, "value": null}', 'sahne', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:39:20.41156+02');
INSERT INTO public.products VALUES ('p-0012', 'Cola', 'Cola', 'Freeway', '{"unit": null, "count": 1, "value": null}', 'limonade', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:39:49.191292+02');
INSERT INTO public.products VALUES ('p-0014', 'Bananen', 'Bananen', NULL, '{"unit": null, "count": 1, "value": null}', 'bananen', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:40:30.582882+02');
INSERT INTO public.products VALUES ('p-0015', 'Gouda', 'Gouda', NULL, '{"unit": null, "count": 1, "value": null}', 'schnittkaese', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{jung,Scheiben}', NULL, '2026-10-19 16:40:30.585827+02');
INSERT INTO public.products VALUES ('p-0016', 'Edel-Vollmilchschokolade', 'Edel-Vollmilchschokolade', 'Moser Roth', '{"unit": null, "count": 1, "value": null}', 'schokolade', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:42:20.198712+02');
INSERT INTO public.products VALUES ('p-0017', 'Toilettenpapier', 'Toilettenpapier', 'Kokett', '{"unit": null, "count": 1, "value": null}', 'toilettenpapier', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:43:29.862476+02');
INSERT INTO public.products VALUES ('p-0019', 'Salatgurke', 'Salatgurke', NULL, '{"unit": null, "count": 1, "value": null}', 'gurken', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:44:11.854801+02');
INSERT INTO public.products VALUES ('p-0020', 'Bio Eier', 'Bio Eier', NULL, '{"unit": null, "count": 1, "value": null}', 'eier-kat', true, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Freiland}', NULL, '2026-10-19 16:44:11.857618+02');
INSERT INTO public.products VALUES ('p-0022', 'Toastbrot', 'Toastbrot', 'Globus', '{"unit": null, "count": 1, "value": null}', 'toastbrot', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Weizen}', NULL, '2026-10-19 16:49:47.769734+02');
INSERT INTO public.products VALUES ('p-0024', 'Bio Haferflocken', 'Bio Haferflocken', NULL, '{"unit": null, "count": 1, "value": null}', 'muesli', true, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:49:47.778513+02');
INSERT INTO public.products VALUES ('p-0025', 'Spaghetti', 'Spaghetti', 'Barilla', '{"unit": null, "count": 1, "value": null}', 'nudeln', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{"No. 5"}', '{"file": "b9eab1968a5a829560a6efaac4de0d4b08ea436c70e7877b6c6ff0674d53a102", "from": "barilla.com", "page": "https://www.barilla.com/de-ch/produkte/pasta/klassische-sorten/spaghetti-no-5", "source": "https://images.ctfassets.net/niz9afzgmmyd/7CvrMvbck6gF20dF5wJ1id/ecf3e0aecc8811c4f5f658392750c26f/Spaghettini_No3_500g_Pack_frontal.png"}', '2026-10-19 16:49:59.746062+02');
INSERT INTO public.products VALUES ('p-0026', 'Haferflocken', 'Haferflocken', 'ja!', '{"unit": null, "count": 1, "value": null}', 'muesli', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:50:12.748233+02');
INSERT INTO public.products VALUES ('p-0027', 'Spaghetti', 'Spaghetti', 'K-Classic', '{"unit": null, "count": 1, "value": null}', 'nudeln', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:51:30.090717+02');
INSERT INTO public.products VALUES ('p-0028', 'Passierte Tomaten', 'Passierte Tomaten', 'Mutti', '{"unit": null, "count": 1, "value": null}', 'gemuesekonserven', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', '{"file": "3076b40b2870ee7543dcbcaf6a459eea9d76c2c2b966578515e45d97caabc2ce", "from": "mutti-parma.com", "page": "https://mutti-parma.com/de/produkte/passierte-tomaten/", "source": "https://mutti-parma.com/app/uploads/sites/15/2019/10/63062-63087-passata-700g-passata.png"}', '2026-10-19 16:30:19.592841+02');
INSERT INTO public.products VALUES ('p-0004', 'Frische Milch', 'Frische Milch', 'Weihenstephan', '{"unit": null, "count": 1, "value": null}', 'milch', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{"3,5%"}', '{"file": "d7349ce5942d292f216560f9c736bc661b22bc04c3c9e348116711939c7c2587", "from": "rewe.de", "page": "https://www.rewe.de/shop/p/weihenstephan-frische-milch-3-5-0-5l/547965", "source": "https://img.rewe-static.de/0547965/21421542_digital-image.png"}', '2026-10-19 16:34:41.160711+02');
INSERT INTO public.products VALUES ('p-0013', 'Zahncreme', 'Zahncreme', 'Cien', '{"unit": null, "count": 1, "value": null}', 'zahnpflege', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:40:30.575076+02');
INSERT INTO public.products VALUES ('p-0029', 'Taschentücher', 'Taschentücher', 'Tempo', '{"unit": null, "count": 1, "value": null}', 'taschentuecher', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 16:52:09.379396+02');
INSERT INTO public.products VALUES ('p-0007', 'Frischkäse', 'Frischkäse', 'Philadelphia', '{"unit": null, "count": 1, "value": null}', 'frischkaese', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Original}', NULL, '2026-10-19 16:25:48.081964+02');
INSERT INTO public.products VALUES ('p-0023', 'Pizza Salami', 'Pizza Salami', 'Dr. Oetker', '{"unit": null, "count": 1, "value": null}', 'pizza', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Ristorante}', '{"file": "81be3c256a151f540a67281d345ff26140009b80809cbbfe06ef85be7c5ed610", "from": "rewe.de", "page": "https://www.rewe.de/shop/p/dr-oetker-ristorante-pizza-salame-320g/8704774", "source": "https://img.rewe-static.de/8704774/34878457_digital-image.png"}', '2026-10-19 16:29:02.104616+02');
INSERT INTO public.products VALUES ('p-0018', 'Duschgel', 'Duschgel', 'Lacura', '{"unit": null, "count": 1, "value": null}', 'duschgel', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', '{"file": "7d9c3143c3c7deea1051340fd6b00c4639a52d7c0544cb9b3fa857680754d0a2", "from": "aldi-sued.de", "page": "https://www.aldi-sued.de/produkt/lacura-duschgel-400-ml-zitrone-000000000530596001", "source": "https://dm.emea.cms.aldi.cx/is/image/aldiprodeu/product/jpg/scaleWidth/300/8855906f-3790-432c-a6d0-1a884ee0db41/Duschgel%20400%20ml%20Zitrone"}', '2026-10-19 16:44:11.848931+02');
INSERT INTO public.products VALUES ('p-0030', 'Alpenmilchschokolade', 'Alpenmilchschokolade', 'Ritter Sport', '{"unit": null, "count": 1, "value": null}', 'schokolade', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 17:18:54.05101+02');
INSERT INTO public.products VALUES ('p-0031', 'Nutella', 'Nutella', NULL, '{"unit": null, "count": 1, "value": null}', 'schokocreme', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 17:18:54.054087+02');
INSERT INTO public.products VALUES ('p-0032', 'Erdbeeren', 'Erdbeeren', NULL, '{"unit": null, "count": 1, "value": null}', 'beeren', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 17:18:54.055451+02');
INSERT INTO public.products VALUES ('p-0033', 'Goldbären', 'Goldbären', 'Haribo', '{"unit": null, "count": 1, "value": null}', 'fruchtgummi', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 17:19:24.154035+02');
INSERT INTO public.products VALUES ('p-0034', 'Spülmittel', 'Spülmittel', 'Frosch', '{"unit": null, "count": 1, "value": null}', 'spuelmittel', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Zitrone}', NULL, '2026-10-19 17:20:03.240781+02');
INSERT INTO public.products VALUES ('p-0035', 'Pesto', 'Pesto', 'Cucina', '{"unit": null, "count": 1, "value": null}', 'saucen', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Verde}', NULL, '2026-10-19 17:22:07.361012+02');
INSERT INTO public.products VALUES ('p-0036', 'Lebkuchen', 'Lebkuchen', NULL, '{"unit": null, "count": 1, "value": null}', 'suessgebaeck', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Herzen}', NULL, '2026-10-19 17:22:07.365477+02');
INSERT INTO public.products VALUES ('p-0037', 'Avocado', 'Avocado', NULL, '{"unit": null, "count": 1, "value": null}', 'exotisches-obst', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Hass}', NULL, '2026-10-19 17:22:07.367905+02');
INSERT INTO public.products VALUES ('p-0038', 'Schokolade', 'Schokolade', 'Lindt', '{"unit": null, "count": 1, "value": null}', 'schokolade', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Excellence,70%}', NULL, '2026-10-19 17:22:35.105643+02');
INSERT INTO public.products VALUES ('p-0039', 'Rinderhackfleisch', 'Rinderhackfleisch', NULL, '{"unit": null, "count": 1, "value": null}', 'hackfleisch', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 17:22:35.11108+02');
INSERT INTO public.products VALUES ('p-0040', 'Espressobohnen', 'Espressobohnen', 'Bellarom', '{"unit": null, "count": 1, "value": null}', 'kaffee', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-19 17:42:36.151797+02');


--
-- Data for Name: questions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: receipt_lines; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.receipt_lines VALUES (1, 1, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (2, 1, 1, 'product', 'Hähnchenbrustfilet 400g', 1, NULL, 4.49, 0.00, 4.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (3, 1, 2, 'product', 'Milsani Joghurt Natur 500g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (4, 2, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.45, 0.00, 1.45, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (5, 2, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.49, 0.00, 2.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (6, 2, 2, 'product', 'Rispentomaten', 1, NULL, 1.87, 0.00, 1.87, '2', true, 0.625, 2.99, 'kg');
INSERT INTO public.receipt_lines VALUES (7, 2, 3, 'product', 'Philadelphia Original 175g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (8, 2, 4, 'product', 'Coca-Cola 1,5L', 2, 1.69, 3.38, 0.00, 3.38, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (9, 2, 5, 'deposit', 'Pfand', 2, NULL, 0.50, 0.00, 0.50, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (10, 3, 0, 'product', 'Milbona Frische Vollmilch 1L', 1, NULL, 1.09, 0.00, 1.09, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (11, 3, 1, 'product', 'Barissimo Crema Bohnen 1kg', 1, NULL, 12.99, 0.00, 12.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (12, 3, 2, 'product', 'Pilos Schmand 200g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (13, 3, 3, 'product', 'Freeway Cola 1,5L', 2, 0.65, 1.30, 0.00, 1.30, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (14, 3, 4, 'deposit', 'Pfand', 2, NULL, 0.50, 0.00, 0.50, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (15, 3, 5, 'product', 'Cien Zahncreme 125ml', 1, NULL, 0.65, 0.00, 0.65, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (16, 4, 0, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (17, 4, 1, 'product', 'Hähnchenbrustfilet 400g', 1, NULL, 4.49, 0.00, 4.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (18, 4, 2, 'product', 'Milsani Joghurt Natur 500g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (19, 4, 3, 'product', 'Gouda jung Scheiben 400g', 2, 2.79, 5.58, 0.00, 5.58, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (20, 4, 4, 'product', 'Moser Roth Edel-Vollmilch', 1, NULL, 1.39, 0.00, 1.39, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (21, 4, 5, 'product', 'Kokett Toilettenpapier 8x', 1, NULL, 2.99, 0.00, 2.99, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (22, 4, 6, 'product', 'Lacura Duschgel 300ml', 1, NULL, 0.89, 0.00, 0.89, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (23, 5, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.45, 0.00, 1.45, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (24, 5, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.49, 0.00, 2.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (25, 5, 2, 'product', 'Bananen', 1, NULL, 1.35, 0.00, 1.35, '2', true, 0.909, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (26, 5, 3, 'product', 'Rispentomaten', 1, NULL, 1.96, 0.00, 1.96, '2', true, 0.654, 2.99, 'kg');
INSERT INTO public.receipt_lines VALUES (27, 5, 4, 'product', 'Salatgurke St.', 1, NULL, 0.79, 0.00, 0.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (28, 5, 5, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, -0.80, 3.19, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (29, 5, 6, 'product', 'Philadelphia Original 175g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (30, 5, 7, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (31, 5, 8, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (32, 5, 9, 'product', 'Globus Toastbrot Weizen 500g', 2, 0.99, 1.98, 0.00, 1.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (33, 6, 0, 'product', 'K-Classic Spaghetti 500g', 2, 0.79, 1.58, 0.00, 1.58, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (34, 6, 1, 'product', 'Kerrygold Butter 250g', 2, 2.39, 4.78, -1.43, 3.35, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (35, 6, 2, 'product', 'Ritter Sport Alpenmilch 100g', 2, 1.49, 2.98, -0.60, 2.38, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (36, 6, 3, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.59, 0.00, 1.59, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (37, 6, 4, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (38, 7, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 2, 1.45, 2.90, -0.58, 2.32, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (39, 7, 1, 'product', 'Bananen', 1, NULL, 1.49, 0.00, 1.49, '2', true, 0.998, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (40, 7, 2, 'product', 'Rispentomaten', 1, NULL, 1.35, 0.00, 1.35, '2', true, 0.453, 2.99, 'kg');
INSERT INTO public.receipt_lines VALUES (41, 7, 3, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (42, 7, 4, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (43, 7, 5, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (44, 7, 6, 'product', 'Ja! Haferflocken 500g', 2, 0.89, 1.78, 0.00, 1.78, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (45, 8, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (46, 8, 1, 'product', 'Bananen', 2, 1.19, 2.38, 0.00, 2.38, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (47, 8, 2, 'product', 'Milsani Joghurt Natur 500g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (48, 8, 3, 'product', 'Gouda jung Scheiben 400g', 1, NULL, 2.79, 0.00, 2.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (49, 8, 4, 'product', 'Bio Haferflocken 500g', 2, 0.99, 1.98, 0.00, 1.98, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (50, 9, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.45, 0.00, 1.45, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (51, 9, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.49, 0.00, 2.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (52, 9, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (53, 9, 3, 'product', 'Mutti Passata 500g', 1, NULL, 1.29, -0.39, 0.90, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (54, 9, 4, 'product', 'Bananen', 1, NULL, 2.03, 0.00, 2.03, '2', true, 1.362, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (55, 9, 5, 'product', 'Salatgurke St.', 1, NULL, 0.79, 0.00, 0.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (56, 9, 6, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (57, 9, 7, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.69, 0.00, 1.69, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (58, 9, 8, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (59, 9, 9, 'product', 'Nutella 450g', 1, NULL, 3.49, 0.00, 3.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (60, 9, 10, 'product', 'Erdbeeren 500g', 2, 2.99, 5.98, 0.00, 5.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (61, 10, 0, 'product', 'Milbona Frische Vollmilch 1L', 2, 1.09, 2.18, 0.00, 2.18, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (62, 10, 1, 'product', 'Barissimo Crema Bohnen 1kg', 2, 12.99, 25.98, 0.00, 25.98, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (63, 10, 2, 'product', 'Pilos Schmand 200g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (64, 10, 3, 'product', 'Nutella 450g', 1, NULL, 3.29, 0.00, 3.29, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (65, 10, 4, 'product', 'Freeway Cola 1,5L', 1, NULL, 0.65, 0.00, 0.65, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (66, 10, 5, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (67, 11, 0, 'product', 'Milsani H-Milch 1,5% 1L', 2, 0.99, 1.98, 0.00, 1.98, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (68, 11, 1, 'product', 'Milsani Joghurt Natur 500g', 2, 0.79, 1.58, 0.00, 1.58, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (69, 11, 2, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (70, 12, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.45, 0.00, 1.45, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (71, 12, 1, 'product', 'Barilla Spaghetti No.5 500g', 2, 1.79, 3.58, 0.00, 3.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (72, 12, 2, 'product', 'Bananen', 1, NULL, 1.53, 0.00, 1.53, '2', true, 1.026, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (73, 12, 3, 'product', 'Rispentomaten', 1, NULL, 1.53, 0.00, 1.53, '2', true, 0.512, 2.99, 'kg');
INSERT INTO public.receipt_lines VALUES (74, 12, 4, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (75, 12, 5, 'product', 'Philadelphia Original 175g', 1, NULL, 1.99, -0.60, 1.39, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (76, 12, 6, 'product', 'Haribo Goldbären 175g', 1, NULL, 1.29, 0.00, 1.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (155, 24, 0, 'deposit_return', 'Leergut', 1, NULL, NULL, NULL, -1.50, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (77, 12, 7, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, -0.24, 0.55, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (78, 12, 8, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (79, 12, 9, 'product', 'Ja! Haferflocken 500g', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (80, 13, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (81, 13, 1, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (82, 13, 2, 'product', 'Gouda jung Scheiben 400g', 1, NULL, 2.79, 0.00, 2.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (83, 13, 3, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (84, 13, 4, 'product', 'Kokett Toilettenpapier 8x', 1, NULL, 2.99, 0.00, 2.99, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (85, 14, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.45, 0.00, 1.45, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (86, 14, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.69, 0.00, 2.69, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (87, 14, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (88, 14, 3, 'product', 'Mutti Passata 500g', 1, NULL, 1.29, -0.26, 1.03, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (89, 14, 4, 'product', 'Bananen', 1, NULL, 1.75, 0.00, 1.75, '2', true, 1.174, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (90, 14, 5, 'product', 'Rispentomaten', 1, NULL, 2.24, 0.00, 2.24, '2', true, 0.748, 2.99, 'kg');
INSERT INTO public.receipt_lines VALUES (91, 14, 6, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (92, 15, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.49, 0.00, 1.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (93, 15, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.69, 0.00, 2.69, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (94, 15, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (95, 15, 3, 'product', 'Rispentomaten', 1, NULL, 2.00, 0.00, 2.00, '2', true, 0.669, 2.99, 'kg');
INSERT INTO public.receipt_lines VALUES (96, 15, 4, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (97, 15, 5, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (98, 15, 6, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (99, 15, 7, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (100, 15, 8, 'product', 'Erdbeeren 500g', 1, NULL, 2.99, 0.00, 2.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (101, 16, 0, 'product', 'K-Classic Spaghetti 500g', 1, NULL, 0.79, 0.00, 0.79, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (102, 16, 1, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.69, 0.00, 1.69, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (103, 16, 2, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.59, 0.00, 2.59, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (104, 16, 3, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.59, 0.00, 1.59, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (105, 16, 4, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (106, 16, 5, 'product', 'Mutti Passata 500g', 1, NULL, 1.19, 0.00, 1.19, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (107, 17, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (108, 17, 1, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (109, 18, 0, 'deposit_return', 'Leergut', 1, NULL, NULL, NULL, -1.25, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (110, 18, 1, 'product', 'Milbona Frische Vollmilch 1L', 1, NULL, 1.09, 0.00, 1.09, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (111, 18, 2, 'product', 'Cien Zahncreme 125ml', 2, 0.65, 1.30, 0.00, 1.30, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (112, 19, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 2, 1.49, 2.98, 0.00, 2.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (113, 19, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.69, 0.00, 2.69, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (114, 19, 2, 'product', 'Mutti Passata 500g', 1, NULL, 1.29, 0.00, 1.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (115, 19, 3, 'product', 'Rispentomaten', 1, NULL, 2.25, 0.00, 2.25, '2', true, 0.754, 2.99, 'kg');
INSERT INTO public.receipt_lines VALUES (116, 19, 4, 'product', 'Salatgurke St.', 1, NULL, 0.59, 0.00, 0.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (117, 19, 5, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (118, 19, 6, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (119, 19, 7, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (120, 19, 8, 'product', 'Ja! Haferflocken 500g', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (121, 19, 9, 'product', 'Erdbeeren 500g', 1, NULL, 2.49, 0.00, 2.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (122, 20, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (123, 20, 1, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (124, 20, 2, 'product', 'Hähnchenbrustfilet 400g', 1, NULL, 4.79, 0.00, 4.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (125, 20, 3, 'product', 'Lacura Duschgel 300ml', 2, 0.89, 1.78, 0.00, 1.78, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (126, 21, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.49, 0.00, 1.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (127, 21, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.69, 0.00, 2.69, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (128, 21, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (129, 21, 3, 'product', 'Mutti Passata 500g', 2, 1.29, 2.58, 0.00, 2.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (130, 21, 4, 'product', 'Bananen', 1, NULL, 1.97, 0.00, 1.97, '2', true, 1.325, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (131, 21, 5, 'product', 'Rispentomaten', 1, NULL, 1.97, 0.00, 1.97, '2', true, 0.791, 2.49, 'kg');
INSERT INTO public.receipt_lines VALUES (132, 21, 6, 'product', 'Salatgurke St.', 1, NULL, 0.59, -0.12, 0.47, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (133, 21, 7, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (134, 21, 8, 'product', 'Philadelphia Original 175g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (135, 21, 9, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (136, 21, 10, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (137, 21, 11, 'product', 'Erdbeeren 500g', 1, NULL, 2.49, -0.75, 1.74, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (138, 22, 0, 'deposit_return', 'Leergut', 1, NULL, NULL, NULL, -2.00, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (139, 22, 1, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.49, 0.00, 1.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (140, 22, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (141, 22, 3, 'product', 'Bananen', 1, NULL, 1.39, 0.00, 1.39, '2', true, 0.934, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (142, 22, 4, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (143, 22, 5, 'product', 'Dr.Oetker Ristorante Salame', 2, 2.79, 5.58, 0.00, 5.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (144, 22, 6, 'product', 'Haribo Goldbären 175g', 1, NULL, 1.29, 0.00, 1.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (145, 22, 7, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.79, 0.00, 1.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (146, 22, 8, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (147, 22, 9, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (148, 22, 10, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (149, 22, 11, 'product', 'Tempo Taschent. 10x10', 1, NULL, 2.29, 0.00, 2.29, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (150, 23, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (151, 23, 1, 'product', 'Hähnchenbrustfilet 400g', 2, 4.79, 9.58, 0.00, 9.58, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (152, 23, 2, 'product', 'Gouda jung Scheiben 400g', 2, 2.79, 5.58, 0.00, 5.58, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (153, 23, 3, 'product', 'Moser Roth Edel-Vollmilch', 1, NULL, 1.39, 0.00, 1.39, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (154, 23, 4, 'product', 'Bio Haferflocken 500g', 2, 0.99, 1.98, 0.00, 1.98, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (156, 24, 1, 'product', 'Milbona Frische Vollmilch 1L', 2, 1.09, 2.18, 0.00, 2.18, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (157, 24, 2, 'product', 'Nutella 450g', 1, NULL, 3.29, 0.00, 3.29, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (158, 25, 0, 'deposit_return', 'Leergut', 1, NULL, NULL, NULL, -2.00, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (159, 25, 1, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.49, 0.00, 1.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (160, 25, 2, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.69, 0.00, 2.69, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (161, 25, 3, 'product', 'Bananen', 1, NULL, 1.43, 0.00, 1.43, '2', true, 0.960, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (162, 25, 4, 'product', 'Salatgurke St.', 1, NULL, 0.59, 0.00, 0.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (163, 25, 5, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (164, 25, 6, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (165, 25, 7, 'product', 'Haribo Goldbären 175g', 1, NULL, 1.29, 0.00, 1.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (166, 25, 8, 'product', 'Tempo Taschent. 10x10', 1, NULL, 2.29, 0.00, 2.29, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (167, 25, 9, 'product', 'Globus Toastbrot Weizen 500g', 2, 0.99, 1.98, 0.00, 1.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (168, 25, 10, 'product', 'Ja! Haferflocken 500g', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (169, 25, 11, 'product', 'Nutella 450g', 1, NULL, 3.49, 0.00, 3.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (170, 25, 12, 'product', 'Erdbeeren 500g', 1, NULL, 2.49, 0.00, 2.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (171, 26, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (172, 26, 1, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (173, 26, 2, 'product', 'Hähnchenbrustfilet 400g', 1, NULL, 4.79, 0.00, 4.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (174, 26, 3, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (175, 26, 4, 'product', 'Kokett Toilettenpapier 8x', 2, 2.99, 5.98, 0.00, 5.98, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (176, 27, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 2, 1.49, 2.98, 0.00, 2.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (177, 27, 1, 'product', 'Kerrygold Butter 250g', 2, 2.89, 5.78, 0.00, 5.78, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (178, 27, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (179, 27, 3, 'product', 'Mutti Passata 500g', 1, NULL, 1.39, 0.00, 1.39, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (180, 27, 4, 'product', 'Bananen', 1, NULL, 1.95, 0.00, 1.95, '2', true, 1.312, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (181, 27, 5, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (182, 27, 6, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.79, 0.00, 1.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (183, 27, 7, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (184, 27, 8, 'product', 'Erdbeeren 500g', 1, NULL, 2.49, 0.00, 2.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (185, 28, 0, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.69, 0.00, 1.69, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (186, 28, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.59, 0.00, 2.59, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (187, 28, 2, 'product', 'Ritter Sport Alpenmilch 100g', 1, NULL, 1.69, 0.00, 1.69, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (188, 28, 3, 'product', 'Frosch Spülmittel Zitrone', 2, 1.19, 2.38, 0.00, 2.38, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (189, 29, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.49, 0.00, 1.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (190, 29, 1, 'product', 'Kerrygold Butter 250g', 2, 2.89, 5.78, 0.00, 5.78, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (191, 29, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, -0.36, 1.43, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (192, 29, 3, 'product', 'Mutti Passata 500g', 1, NULL, 1.39, 0.00, 1.39, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (193, 29, 4, 'product', 'Bananen', 1, NULL, 1.66, 0.00, 1.66, '2', true, 1.112, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (194, 29, 5, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (195, 29, 6, 'product', 'Philadelphia Original 175g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (196, 29, 7, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (197, 29, 8, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (198, 29, 9, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (199, 29, 10, 'product', 'Globus Toastbrot Weizen 500g', 1, NULL, 0.99, 0.00, 0.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (200, 30, 0, 'product', 'Milsani H-Milch 1,5% 1L', 2, 0.99, 1.98, 0.00, 1.98, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (201, 30, 1, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (202, 30, 2, 'product', 'Gouda jung Scheiben 400g', 1, NULL, 2.99, 0.00, 2.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (203, 31, 0, 'product', 'Barissimo Crema Bohnen 1kg', 1, NULL, 13.99, 0.00, 13.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (204, 31, 1, 'product', 'Bananen lose', 1, NULL, 1.25, 0.00, 1.25, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (205, 31, 2, 'product', 'Salatgurke', 2, 0.59, 1.18, -0.24, 0.94, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (206, 31, 3, 'product', 'Nutella 450g', 1, NULL, 3.29, 0.00, 3.29, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (207, 31, 4, 'product', 'Freeway Cola 1,5L', 1, NULL, 0.65, 0.00, 0.65, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (208, 31, 5, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (209, 31, 6, 'product', 'Cien Zahncreme 125ml', 1, NULL, 0.65, 0.00, 0.65, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (210, 32, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 2, 1.49, 2.98, 0.00, 2.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (211, 32, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.89, 0.00, 2.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (212, 32, 2, 'product', 'Bananen', 1, NULL, 1.88, 0.00, 1.88, '2', true, 1.265, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (213, 32, 3, 'product', 'Rispentomaten', 1, NULL, 1.44, 0.00, 1.44, '2', true, 0.579, 2.49, 'kg');
INSERT INTO public.receipt_lines VALUES (214, 32, 4, 'product', 'Philadelphia Original 175g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (215, 32, 5, 'product', 'Coca-Cola 1,5L', 2, 1.79, 3.58, 0.00, 3.58, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (216, 32, 6, 'deposit', 'Pfand', 2, NULL, 0.50, 0.00, 0.50, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (217, 32, 7, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (218, 32, 8, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (219, 32, 9, 'product', 'Ja! Haferflocken 500g', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (220, 33, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (221, 33, 1, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (222, 33, 2, 'product', 'Gouda jung Scheiben 400g', 1, NULL, 2.99, 0.00, 2.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (223, 33, 3, 'product', 'Kokett Toilettenpapier 8x', 1, NULL, 2.99, 0.00, 2.99, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (224, 33, 4, 'product', 'Lacura Duschgel 300ml', 1, NULL, 0.89, 0.00, 0.89, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (225, 34, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.49, 0.00, 1.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (226, 34, 1, 'product', 'Kerrygold Butter 250g', 2, 2.89, 5.78, 0.00, 5.78, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (227, 34, 2, 'product', 'Mutti Passata 500g', 1, NULL, 1.39, 0.00, 1.39, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (228, 34, 3, 'product', 'Rispentomaten', 1, NULL, 1.57, 0.00, 1.57, '2', true, 0.630, 2.49, 'kg');
INSERT INTO public.receipt_lines VALUES (229, 34, 4, 'product', 'Salatgurke St.', 2, 0.59, 1.18, 0.00, 1.18, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (230, 34, 5, 'product', 'Bio Eier Freiland 10St', 2, 3.99, 7.98, 0.00, 7.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (231, 34, 6, 'product', 'Globus Toastbrot Weizen 500g', 2, 0.99, 1.98, 0.00, 1.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (232, 35, 0, 'product', 'Kerrygold Butter 250g', 2, 2.89, 5.78, 0.00, 5.78, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (233, 35, 1, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (234, 35, 2, 'product', 'Bananen', 1, NULL, 2.08, 0.00, 2.08, '2', true, 1.397, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (235, 35, 3, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (236, 35, 4, 'product', 'Philadelphia Original 175g', 2, 1.99, 3.98, 0.00, 3.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (237, 35, 5, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.99, 0.00, 2.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (238, 35, 6, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.79, 0.00, 1.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (239, 35, 7, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (240, 35, 8, 'product', 'Tempo Taschent. 10x10', 1, NULL, 2.29, 0.00, 2.29, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (241, 36, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 1.05, 0.00, 1.05, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (242, 36, 1, 'product', 'Moser Roth Edel-Vollmilch', 2, 1.39, 2.78, 0.00, 2.78, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (243, 36, 2, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (244, 37, 0, 'product', 'Barissimo Crema Bohnen 1kg', 1, NULL, 13.99, 0.00, 13.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (245, 37, 1, 'product', 'Bananen lose', 1, NULL, 1.25, 0.00, 1.25, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (246, 37, 2, 'product', 'Pilos Schmand 200g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (247, 38, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.55, 0.00, 1.55, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (248, 38, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.89, 0.00, 2.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (249, 38, 2, 'product', 'Rispentomaten', 1, NULL, 1.58, 0.00, 1.58, '2', true, 0.634, 2.49, 'kg');
INSERT INTO public.receipt_lines VALUES (250, 38, 3, 'product', 'Salatgurke St.', 1, NULL, 0.59, 0.00, 0.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (251, 38, 4, 'product', 'Bio Eier Freiland 10St', 1, NULL, 3.99, 0.00, 3.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (252, 38, 5, 'product', 'Haribo Goldbären 175g', 1, NULL, 1.29, 0.00, 1.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (253, 38, 6, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (254, 38, 7, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (255, 38, 8, 'product', 'Globus Toastbrot Weizen 500g', 1, NULL, 0.99, 0.00, 0.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (256, 38, 9, 'product', 'Nutella 450g', 1, NULL, 3.79, 0.00, 3.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (257, 39, 0, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.59, 0.00, 2.59, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (258, 39, 1, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.59, 0.00, 1.59, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (259, 39, 2, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (260, 39, 3, 'product', 'Frosch Spülmittel Zitrone', 2, 1.19, 2.38, 0.00, 2.38, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (261, 40, 0, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (262, 40, 1, 'product', 'Hähnchenbrustfilet 400g', 2, 4.79, 9.58, 0.00, 9.58, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (263, 40, 2, 'product', 'Milsani Joghurt Natur 500g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (264, 40, 3, 'product', 'Gouda jung Scheiben 400g', 1, NULL, 2.99, 0.00, 2.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (265, 40, 4, 'product', 'Cucina Pesto Verde 190g', 1, NULL, 1.49, 0.00, 1.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (266, 41, 0, 'deposit_return', 'Leergut', 1, NULL, NULL, NULL, -1.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (267, 41, 1, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.55, 0.00, 1.55, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (268, 41, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (269, 41, 3, 'product', 'Rispentomaten', 1, NULL, 1.27, 0.00, 1.27, '2', true, 0.511, 2.49, 'kg');
INSERT INTO public.receipt_lines VALUES (270, 41, 4, 'product', 'Salatgurke St.', 1, NULL, 0.59, 0.00, 0.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (271, 41, 5, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.99, 0.00, 2.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (272, 42, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.55, -0.31, 1.24, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (273, 42, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.89, 0.00, 2.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (274, 42, 2, 'product', 'Bananen', 1, NULL, 2.00, 0.00, 2.00, '2', true, 1.345, 1.49, 'kg');
INSERT INTO public.receipt_lines VALUES (275, 42, 3, 'product', 'Bio Eier Freiland 10St', 2, 3.99, 7.98, 0.00, 7.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (276, 42, 4, 'product', 'Haribo Goldbären 175g', 2, 1.29, 2.58, 0.00, 2.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (277, 42, 5, 'product', 'Globus Toastbrot Weizen 500g', 1, NULL, 1.09, 0.00, 1.09, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (278, 42, 6, 'product', 'Nutella 450g', 2, 3.79, 7.58, 0.00, 7.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (279, 43, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 1.05, 0.00, 1.05, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (280, 43, 1, 'product', 'Hähnchenbrustfilet 400g', 2, 4.79, 9.58, 0.00, 9.58, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (281, 43, 2, 'product', 'Cucina Pesto Verde 190g', 1, NULL, 1.49, 0.00, 1.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (282, 44, 0, 'product', 'Milbona Frische Vollmilch 1L', 2, 1.15, 2.30, 0.00, 2.30, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (283, 44, 1, 'product', 'Bananen lose', 1, NULL, 1.25, 0.00, 1.25, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (284, 45, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.55, 0.00, 1.55, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (285, 45, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.89, 0.00, 2.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (286, 45, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.99, -0.40, 1.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (287, 45, 3, 'product', 'Rispentomaten', 1, NULL, 1.46, 0.00, 1.46, '2', true, 0.588, 2.49, 'kg');
INSERT INTO public.receipt_lines VALUES (288, 45, 4, 'product', 'Salatgurke St.', 1, NULL, 0.59, 0.00, 0.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (289, 45, 5, 'product', 'Bio Eier Freiland 10St', 1, NULL, 4.29, 0.00, 4.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (290, 45, 6, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.99, 0.00, 2.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (291, 45, 7, 'product', 'Haribo Goldbären 175g', 2, 1.29, 2.58, 0.00, 2.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (292, 45, 8, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.79, -0.54, 1.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (293, 45, 9, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (294, 45, 10, 'product', 'Gerolsteiner Naturell 1,5L', 2, 0.79, 1.58, 0.00, 1.58, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (295, 45, 11, 'deposit', 'Pfand', 2, NULL, 0.50, 0.00, 0.50, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (296, 45, 12, 'product', 'Globus Toastbrot Weizen 500g', 1, NULL, 1.09, 0.00, 1.09, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (297, 46, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 1.05, 0.00, 1.05, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (298, 46, 1, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (299, 46, 2, 'product', 'Moser Roth Edel-Vollmilch', 1, NULL, 1.39, 0.00, 1.39, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (300, 46, 3, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (301, 46, 4, 'product', 'Lacura Duschgel 300ml', 1, NULL, 0.89, 0.00, 0.89, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (302, 46, 5, 'product', 'Lebkuchen Herzen 500g', 1, NULL, 2.49, 0.00, 2.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (303, 47, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.55, 0.00, 1.55, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (304, 47, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.89, 0.00, 2.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (305, 47, 2, 'product', 'Mutti Passata 500g', 1, NULL, 1.39, 0.00, 1.39, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (306, 47, 3, 'product', 'Bananen', 1, NULL, 2.03, 0.00, 2.03, '2', true, 1.200, 1.69, 'kg');
INSERT INTO public.receipt_lines VALUES (307, 47, 4, 'product', 'Rispentomaten', 1, NULL, 1.70, -0.34, 1.36, '2', true, 0.683, 2.49, 'kg');
INSERT INTO public.receipt_lines VALUES (308, 47, 5, 'product', 'Salatgurke St.', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (309, 47, 6, 'product', 'Bio Eier Freiland 10St', 1, NULL, 4.29, 0.00, 4.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (310, 47, 7, 'product', 'Globus Toastbrot Weizen 500g', 1, NULL, 1.09, 0.00, 1.09, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (311, 47, 8, 'product', 'Ja! Haferflocken 500g', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (312, 48, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 1.05, 0.00, 1.05, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (313, 48, 1, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (314, 48, 2, 'product', 'Gouda jung Scheiben 400g', 1, NULL, 2.99, 0.00, 2.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (315, 48, 3, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (316, 48, 4, 'product', 'Lebkuchen Herzen 500g', 1, NULL, 2.49, 0.00, 2.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (317, 49, 0, 'deposit_return', 'Leergut', 1, NULL, NULL, NULL, -2.00, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (318, 49, 1, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.55, 0.00, 1.55, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (319, 49, 2, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.89, 0.00, 2.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (320, 49, 3, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (321, 49, 4, 'product', 'Rispentomaten', 1, NULL, 1.72, 0.00, 1.72, '2', true, 0.492, 3.49, 'kg');
INSERT INTO public.receipt_lines VALUES (322, 49, 5, 'product', 'Salatgurke St.', 2, 0.89, 1.78, 0.00, 1.78, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (323, 49, 6, 'product', 'Haribo Goldbären 175g', 1, NULL, 1.29, 0.00, 1.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (324, 49, 7, 'product', 'Globus Toastbrot Weizen 500g', 2, 1.09, 2.18, 0.00, 2.18, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (325, 50, 0, 'product', 'K-Classic Spaghetti 500g', 1, NULL, 0.79, -0.24, 0.55, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (326, 51, 0, 'product', 'Milbona Frische Vollmilch 1L', 1, NULL, 1.15, 0.00, 1.15, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (327, 51, 1, 'product', 'Barissimo Crema Bohnen 1kg', 1, NULL, 14.49, 0.00, 14.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (328, 52, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.55, 0.00, 1.55, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (329, 52, 1, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (330, 52, 2, 'product', 'Bananen', 1, NULL, 1.59, 0.00, 1.59, '2', true, 0.943, 1.69, 'kg');
INSERT INTO public.receipt_lines VALUES (331, 52, 3, 'product', 'Salatgurke St.', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (332, 52, 4, 'product', 'Bio Eier Freiland 10St', 1, NULL, 4.29, 0.00, 4.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (333, 52, 5, 'product', 'Globus Toastbrot Weizen 500g', 1, NULL, 1.09, 0.00, 1.09, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (334, 52, 6, 'product', 'Avocado Hass St.', 2, 1.29, 2.58, 0.00, 2.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (335, 53, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 1.05, 0.00, 1.05, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (336, 53, 1, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (337, 53, 2, 'product', 'Hähnchenbrustfilet 400g', 1, NULL, 4.99, 0.00, 4.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (338, 53, 3, 'product', 'Milsani Joghurt Natur 500g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (339, 53, 4, 'product', 'Moser Roth Edel-Vollmilch', 1, NULL, 1.39, 0.00, 1.39, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (340, 53, 5, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (341, 54, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.59, -0.48, 1.11, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (342, 54, 1, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (343, 54, 2, 'product', 'Bananen', 1, NULL, 1.94, 0.00, 1.94, '2', true, 1.149, 1.69, 'kg');
INSERT INTO public.receipt_lines VALUES (344, 54, 3, 'product', 'Rispentomaten', 1, NULL, 2.12, 0.00, 2.12, '2', true, 0.608, 3.49, 'kg');
INSERT INTO public.receipt_lines VALUES (345, 54, 4, 'product', 'Salatgurke St.', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (346, 54, 5, 'product', 'Tempo Taschent. 10x10', 2, 2.29, 4.58, 0.00, 4.58, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (347, 54, 6, 'product', 'Globus Toastbrot Weizen 500g', 1, NULL, 1.09, 0.00, 1.09, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (348, 54, 7, 'product', 'Lindt Excellence 70% 100g', 2, 2.79, 5.58, 0.00, 5.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (349, 54, 8, 'product', 'Rinderhackfleisch 500g', 1, NULL, 5.49, 0.00, 5.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (350, 54, 9, 'product', 'Avocado Hass St.', 2, 1.29, 2.58, 0.00, 2.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (351, 55, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 1.05, 0.00, 1.05, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (352, 55, 1, 'product', 'Hähnchenbrustfilet 400g', 1, NULL, 4.99, 0.00, 4.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (353, 55, 2, 'product', 'Lebkuchen Herzen 500g', 1, NULL, 2.49, 0.00, 2.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (354, 56, 0, 'deposit_return', 'Leergut', 1, NULL, NULL, NULL, -1.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (355, 56, 1, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.59, 0.00, 1.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (356, 56, 2, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (357, 56, 3, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (358, 56, 4, 'product', 'Bananen', 1, NULL, 1.73, 0.00, 1.73, '2', true, 1.024, 1.69, 'kg');
INSERT INTO public.receipt_lines VALUES (359, 56, 5, 'product', 'Rispentomaten', 1, NULL, 2.25, 0.00, 2.25, '2', true, 0.644, 3.49, 'kg');
INSERT INTO public.receipt_lines VALUES (360, 56, 6, 'product', 'Bio Eier Freiland 10St', 1, NULL, 4.29, 0.00, 4.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (361, 56, 7, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.79, 0.00, 1.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (362, 56, 8, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (363, 56, 9, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (364, 56, 10, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (365, 56, 11, 'product', 'Globus Toastbrot Weizen 500g', 1, NULL, 1.09, 0.00, 1.09, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (366, 56, 12, 'product', 'Lindt Excellence 70% 100g', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (367, 56, 13, 'product', 'Rinderhackfleisch 500g', 1, NULL, 5.49, 0.00, 5.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (368, 56, 14, 'product', 'Avocado Hass St.', 2, 1.29, 2.58, 0.00, 2.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (369, 57, 0, 'product', 'Milbona Frische Vollmilch 1L', 1, NULL, 1.15, 0.00, 1.15, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (370, 57, 1, 'product', 'Bellarom Espresso Bohnen 1kg', 2, 11.99, 23.98, 0.00, 23.98, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (371, 57, 2, 'product', 'Bananen lose', 1, NULL, 1.25, 0.00, 1.25, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (372, 57, 3, 'product', 'Salatgurke', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (373, 57, 4, 'product', 'Freeway Cola 1,5L', 1, NULL, 0.65, 0.00, 0.65, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (374, 57, 5, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (375, 58, 0, 'deposit_return', 'Leergut', 1, NULL, NULL, NULL, -1.75, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (376, 58, 1, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.59, 0.00, 1.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (377, 58, 2, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (378, 58, 3, 'product', 'Mutti Passata 500g', 2, 1.39, 2.78, 0.00, 2.78, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (379, 58, 4, 'product', 'Rispentomaten', 1, NULL, 2.03, 0.00, 2.03, '2', true, 0.581, 3.49, 'kg');
INSERT INTO public.receipt_lines VALUES (380, 58, 5, 'product', 'Ja! Haferflocken 500g', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (381, 58, 6, 'product', 'Lindt Excellence 70% 100g', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (382, 59, 0, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (383, 59, 1, 'product', 'Milsani Joghurt Natur 500g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (384, 59, 2, 'product', 'Gouda jung Scheiben 400g', 2, 2.79, 5.58, 0.00, 5.58, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (385, 59, 3, 'product', 'Bio Haferflocken 500g', 2, 0.99, 1.98, 0.00, 1.98, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (386, 60, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.59, 0.00, 1.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (387, 60, 1, 'product', 'Kerrygold Butter 250g', 2, 2.79, 5.58, 0.00, 5.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (388, 60, 2, 'product', 'Mutti Passata 500g', 1, NULL, 1.39, 0.00, 1.39, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (389, 60, 3, 'product', 'Rispentomaten', 1, NULL, 1.42, 0.00, 1.42, '2', true, 0.406, 3.49, 'kg');
INSERT INTO public.receipt_lines VALUES (390, 60, 4, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.99, 0.00, 2.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (391, 60, 5, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (392, 60, 6, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (393, 60, 7, 'product', 'Lindt Excellence 70% 100g', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (394, 60, 8, 'product', 'Rinderhackfleisch 500g', 1, NULL, 5.49, -1.65, 3.84, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (395, 60, 9, 'product', 'Avocado Hass St.', 1, NULL, 1.29, 0.00, 1.29, '2', NULL, NULL, NULL, NULL);


--
-- Data for Name: receipts; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.receipts VALUES (53, '2cd783ea529741102b3fa57b5c5b51101541e882f3128234615055cbf81ccea1', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-09-26', '11:45', 'EUR', 10.40, NULL, '{"7%": 10.4}', '2026-10-19 16:23:09.752644+02', '2cd783ea529741102b3fa57b5c5b51101541e882f3128234615055cbf81ccea1', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (54, 'cb56d44b36d5f5d4800cfcbc796a74611a1d52100825892eeca2cc7ee9f2e4a2', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-10-02', '17:19', 'EUR', 27.37, 0.48, '{"7%": 22.79, "19%": 4.58}', '2026-10-19 16:23:09.80805+02', 'cb56d44b36d5f5d4800cfcbc796a74611a1d52100825892eeca2cc7ee9f2e4a2', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (55, 'e00d40a0d4912a1640d64c4763d961a0d15de8d122329784579b7a37c7881301', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-10-07', '13:07', 'EUR', 8.53, NULL, '{"7%": 8.53}', '2026-10-19 16:23:45.458827+02', 'e00d40a0d4912a1640d64c4763d961a0d15de8d122329784579b7a37c7881301', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (56, '6e24c8679b4b7a57ab0f3544e290029d641300c9cc6f2ee4530534428d51c57a', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-10-09', '09:49', 'EUR', 28.42, NULL, '{"7%": 26.59, "19%": 1.83}', '2026-10-19 16:23:55.067698+02', '6e24c8679b4b7a57ab0f3544e290029d641300c9cc6f2ee4530534428d51c57a', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (57, 'b6ea40c3a5d4125a46c5e751b24ac3ff9ded12335add74a884569c8582ffb62e', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-10-11', '12:54', 'EUR', 28.07, NULL, '{"7%": 27.17, "19%": 0.9}', '2026-10-19 16:24:20.775824+02', 'b6ea40c3a5d4125a46c5e751b24ac3ff9ded12335add74a884569c8582ffb62e', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (58, 'a82ae749a537238236e065e7c74f6ac632c428ab4fc9775679d9dfcc4186755b', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-10-15', '10:59', 'EUR', 11.12, NULL, '{"7%": 12.87, "19%": -1.75}', '2026-10-19 16:24:35.964863+02', 'a82ae749a537238236e065e7c74f6ac632c428ab4fc9775679d9dfcc4186755b', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (59, 'e86aebb5e83311bac36b13445737defd8eeef754e2931a30bbc93b30cce2aaa7', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-10-18', '15:40', 'EUR', 9.54, NULL, '{"7%": 9.54}', '2026-10-19 16:24:40.800814+02', 'e86aebb5e83311bac36b13445737defd8eeef754e2931a30bbc93b30cce2aaa7', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (60, '268635a2ed0d2febdcb742b7d95f2d2a111e32e681dc17686992b30075351659', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-10-19', '19:10', 'EUR', 21.93, 1.65, '{"7%": 20.89, "19%": 1.04}', '2026-10-19 16:24:40.864459+02', '268635a2ed0d2febdcb742b7d95f2d2a111e32e681dc17686992b30075351659', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (18, '4c611496c21e6dea6d4d7d6102253e442ed05d080d16280a49b9f5504b32a4f2', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-06-08', '18:35', 'EUR', 1.14, NULL, '{"7%": 1.09, "19%": 0.05}', '2026-10-19 16:10:39.452596+02', '4c611496c21e6dea6d4d7d6102253e442ed05d080d16280a49b9f5504b32a4f2', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (19, '6cd2df957b63ab967e3b9bd9c3997a400e571d7b8c4e95fc534e2729b64bbafa', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-06-12', '09:30', 'EUR', 18.21, NULL, '{"7%": 17.17, "19%": 1.04}', '2026-10-19 16:10:39.495554+02', '6cd2df957b63ab967e3b9bd9c3997a400e571d7b8c4e95fc534e2729b64bbafa', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (20, '9195c8da4a9395ac264d8b208449688813b430ccc19b9585a7d420e7bdd6ddb6', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-06-19', '18:07', 'EUR', 8.75, NULL, '{"7%": 6.97, "19%": 1.78}', '2026-10-19 16:11:20.792806+02', '9195c8da4a9395ac264d8b208449688813b430ccc19b9585a7d420e7bdd6ddb6', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (21, '2a00d175916ac5985d9be7bbceee3feefd3a4fe1b6d97235dd5bada6b7429a72', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-06-19', '12:13', 'EUR', 21.72, 0.87, '{"7%": 20.68, "19%": 1.04}', '2026-10-19 16:11:20.833117+02', '2a00d175916ac5985d9be7bbceee3feefd3a4fe1b6d97235dd5bada6b7429a72', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (22, 'fe2b114ac08e6eb537ee7b6612a652c236156b5705d364f1e27d702f29b34834', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-06-26', '15:42', 'EUR', 18.90, NULL, '{"7%": 15.53, "19%": 3.37}', '2026-10-19 16:11:27.337792+02', 'fe2b114ac08e6eb537ee7b6612a652c236156b5705d364f1e27d702f29b34834', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (23, 'e653cb99a9d488b6ea9e53f9cb8b4ca86c55c51f0b4ebae8aa5f604eb2232089', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-06-28', '10:23', 'EUR', 19.52, NULL, '{"7%": 19.52}', '2026-10-19 16:11:53.515906+02', 'e653cb99a9d488b6ea9e53f9cb8b4ca86c55c51f0b4ebae8aa5f604eb2232089', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (24, '51574ff5a8804373a8564395d920a053358238171f5a175b60a87fc993c14e67', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-06-30', '16:57', 'EUR', 3.97, NULL, '{"7%": 5.47, "19%": -1.5}', '2026-10-19 16:11:53.567825+02', '51574ff5a8804373a8564395d920a053358238171f5a175b60a87fc993c14e67', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (25, 'e5601394441cdd5506a48b7a4f7b5793aa079bda30dc900635c3fe87d16e9e2e', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-07-02', '11:35', 'EUR', 23.41, NULL, '{"7%": 23.12, "19%": 0.29}', '2026-10-19 16:12:48.59539+02', 'e5601394441cdd5506a48b7a4f7b5793aa079bda30dc900635c3fe87d16e9e2e', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (26, 'e569df420572c3b9a7639556f7548136fe8e75be0de1b4447ff77694ba975cc4', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-07-08', '18:15', 'EUR', 13.94, NULL, '{"7%": 7.96, "19%": 5.98}', '2026-10-19 16:13:34.707487+02', 'e569df420572c3b9a7639556f7548136fe8e75be0de1b4447ff77694ba975cc4', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (27, 'dd62d9e1c00c7abcebc6b2e8dd1ef094fc894a05b50ffdb98c330586318c3c00', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-07-09', '16:13', 'EUR', 22.41, NULL, '{"7%": 20.37, "19%": 2.04}', '2026-10-19 16:13:34.74966+02', 'dd62d9e1c00c7abcebc6b2e8dd1ef094fc894a05b50ffdb98c330586318c3c00', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (28, 'd9b9b5eb50d29780f72500935d81b15a8d010b78317bfa5073a70768115ba686', 'made-up', 'Kaufland', 'Testallee 9, 66119 Saarbrücken', '2026-07-12', '18:24', 'EUR', 8.35, NULL, '{"7%": 5.97, "19%": 2.38}', '2026-10-19 16:13:40.558304+02', 'd9b9b5eb50d29780f72500935d81b15a8d010b78317bfa5073a70768115ba686', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (29, '146cf13e51baa1794f33220e808fe4e094cfa27e5abf84dafc46c1e2cc7c8f90', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-07-17', '17:19', 'EUR', 22.55, 0.36, '{"7%": 21.51, "19%": 1.04}', '2026-10-19 16:14:23.077497+02', '146cf13e51baa1794f33220e808fe4e094cfa27e5abf84dafc46c1e2cc7c8f90', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (30, 'd7b7d7bad23c5a8cf906aaf6d00d48de736c9fe5581ec4a2e84fbf68d5f1a6da', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-07-18', '10:57', 'EUR', 6.16, NULL, '{"7%": 6.16}', '2026-10-19 16:14:23.129488+02', 'd7b7d7bad23c5a8cf906aaf6d00d48de736c9fe5581ec4a2e84fbf68d5f1a6da', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (1, '6cb0e11112b1e587bafd02c7533830f6c7ac1fde6c8ff6ed3b0fc0c2a9aeaf50', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-04-21', '11:37', 'EUR', 6.27, NULL, '{"7%": 6.27}', '2026-10-19 15:23:25.988646+02', '6cb0e11112b1e587bafd02c7533830f6c7ac1fde6c8ff6ed3b0fc0c2a9aeaf50', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (2, '8cedcc92bbd8833038e0a52dcbf6d96dbbb7dd70566d92861dae377e6487e134', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-04-25', '17:05', 'EUR', 11.68, NULL, '{"7%": 7.8, "19%": 3.88}', '2026-10-19 15:29:33.273311+02', '8cedcc92bbd8833038e0a52dcbf6d96dbbb7dd70566d92861dae377e6487e134', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (3, '816bfd963804fe3f1a2834bfebc9f7ce8fda8c27d1dddd56928e04ec33aaf1e2', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-04-27', '12:56', 'EUR', 17.32, NULL, '{"7%": 14.87, "19%": 2.45}', '2026-10-19 15:39:44.634977+02', '816bfd963804fe3f1a2834bfebc9f7ce8fda8c27d1dddd56928e04ec33aaf1e2', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (4, '9e65726090c6a3c9493f8a72be04d1a6be35b8e8e14e40992cc44758fc9db668', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-05-01', '09:59', 'EUR', 17.32, NULL, '{"7%": 13.44, "19%": 3.88}', '2026-10-19 15:49:38.414756+02', '9e65726090c6a3c9493f8a72be04d1a6be35b8e8e14e40992cc44758fc9db668', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (5, 'd45efb4f3124b7f617cc24bd4db303838518b9bb27dc6f6139c7cd38fa373c80', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-05-02', '19:09', 'EUR', 16.24, 0.80, '{"7%": 15.2, "19%": 1.04}', '2026-10-19 15:58:16.622011+02', 'd45efb4f3124b7f617cc24bd4db303838518b9bb27dc6f6139c7cd38fa373c80', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (6, '40f9c8caf3389b70fa8301b3c8b1f35e8f2e4a32ef5733914b22d90db54f7d15', 'made-up', 'Kaufland', 'Testallee 9, 66119 Saarbrücken', '2026-05-02', '12:31', 'EUR', 9.15, 2.03, '{"7%": 7.31, "19%": 1.84}', '2026-10-19 16:03:53.526419+02', '40f9c8caf3389b70fa8301b3c8b1f35e8f2e4a32ef5733914b22d90db54f7d15', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (31, '01e4916f10d96f7be7acaabcc3b4a827341448e0103f9292ab9051397385070c', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-07-20', '18:05', 'EUR', 21.02, 0.24, '{"7%": 19.47, "19%": 1.55}', '2026-10-19 16:14:23.175011+02', '01e4916f10d96f7be7acaabcc3b4a827341448e0103f9292ab9051397385070c', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (32, '50d8e91a713e66db46d28315100b25f1365e080462b2a34349885f86543ea821', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-07-24', '17:14', 'EUR', 17.19, NULL, '{"7%": 12.07, "19%": 5.12}', '2026-10-19 16:16:22.175993+02', '50d8e91a713e66db46d28315100b25f1365e080462b2a34349885f86543ea821', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (33, '63c1569006c87ca4cf837c2527daf1b911a6521e8e2f5c63a9e92a9881d411b1', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-07-29', '14:52', 'EUR', 9.05, NULL, '{"7%": 5.17, "19%": 3.88}', '2026-10-19 16:16:22.235626+02', '63c1569006c87ca4cf837c2527daf1b911a6521e8e2f5c63a9e92a9881d411b1', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (34, '3eb0e26793811675f7dae6cfe60b5352ebb785b38c7b5aaa737f937a4b5543e5', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-07-31', '16:16', 'EUR', 21.37, NULL, '{"7%": 21.37}', '2026-10-19 16:16:22.295131+02', '3eb0e26793811675f7dae6cfe60b5352ebb785b38c7b5aaa737f937a4b5543e5', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (35, '6afc035f6b5ad2f56792947893754c3bccdb2755d186a59fbeb8e470d0d5089a', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-08-06', '16:59', 'EUR', 24.94, NULL, '{"7%": 20.61, "19%": 4.33}', '2026-10-19 16:16:22.344626+02', '6afc035f6b5ad2f56792947893754c3bccdb2755d186a59fbeb8e470d0d5089a', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (36, 'b10fa8c82fbfeb4a3f2a8edd19117d39d899cf66451fe55037f9de4ed0ede909', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-08-08', '12:30', 'EUR', 4.82, NULL, '{"7%": 4.82}', '2026-10-19 16:16:22.392055+02', 'b10fa8c82fbfeb4a3f2a8edd19117d39d899cf66451fe55037f9de4ed0ede909', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (37, 'e674bb2ff3f346163f52a673225cca1701c8fa4ebe8be2bc1e34140505182360', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-08-10', '18:50', 'EUR', 16.03, NULL, '{"7%": 16.03}', '2026-10-19 16:16:22.430287+02', 'e674bb2ff3f346163f52a673225cca1701c8fa4ebe8be2bc1e34140505182360', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (38, '6b0152f44453ec106835c9122deff2802fdbabbb9a1494dd3f9f77543e6eb4d8', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-08-12', '09:56', 'EUR', 17.71, NULL, '{"7%": 16.67, "19%": 1.04}', '2026-10-19 16:16:22.478085+02', '6b0152f44453ec106835c9122deff2802fdbabbb9a1494dd3f9f77543e6eb4d8', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (39, '0ded519ef24e3eea72b76ace3a3b0f2748b5bbbfc180cbae479d83b81468702d', 'made-up', 'Kaufland', 'Testallee 9, 66119 Saarbrücken', '2026-08-15', '15:41', 'EUR', 6.81, NULL, '{"7%": 2.59, "19%": 4.22}', '2026-10-19 16:17:12.755301+02', '0ded519ef24e3eea72b76ace3a3b0f2748b5bbbfc180cbae479d83b81468702d', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (40, '67be5337e0bfaf17a0671dd1f424eb2824e338e8a8d1225288615a2851108948', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-08-18', '10:12', 'EUR', 16.04, NULL, '{"7%": 16.04}', '2026-10-19 16:17:21.852786+02', '67be5337e0bfaf17a0671dd1f424eb2824e338e8a8d1225288615a2851108948', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (41, 'e09dc8c20727c513955da742b529f48f71d920f43f848e1f07a13e1ad4f68596', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-08-20', '17:12', 'EUR', 7.14, NULL, '{"7%": 8.39, "19%": -1.25}', '2026-10-19 16:17:31.033917+02', 'e09dc8c20727c513955da742b529f48f71d920f43f848e1f07a13e1ad4f68596', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (42, '4b11afe29e62d69559f9f0522d602047f75ec4bbc6e02a7544d833910661b8be', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-08-27', '15:12', 'EUR', 25.36, 0.31, '{"7%": 25.36}', '2026-10-19 16:17:31.147967+02', '4b11afe29e62d69559f9f0522d602047f75ec4bbc6e02a7544d833910661b8be', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (43, 'a6617aaf9af69ac2be5c67ffeff2d3f131229e667ea699d055fe9f36de518180', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-08-28', '12:09', 'EUR', 12.12, NULL, '{"7%": 12.12}', '2026-10-19 16:17:57.581504+02', 'a6617aaf9af69ac2be5c67ffeff2d3f131229e667ea699d055fe9f36de518180', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (11, 'f22105fcf4d29355ab2eb00e3ff676e6d4d5fd5efd6b81e1ec1daf318f3a0809', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-05-20', '12:35', 'EUR', 4.55, NULL, '{"7%": 4.55}', '2026-10-19 16:08:27.443815+02', 'f22105fcf4d29355ab2eb00e3ff676e6d4d5fd5efd6b81e1ec1daf318f3a0809', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (12, 'f500632601a483972bbb897eca648ff781de9836f0e1f98014a8cc5561cb3bcb', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-05-23', '11:25', 'EUR', 16.45, 0.84, '{"7%": 15.65, "19%": 0.8}', '2026-10-19 16:08:42.37328+02', 'f500632601a483972bbb897eca648ff781de9836f0e1f98014a8cc5561cb3bcb', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (13, '7e76b37d2f01b663b74cf786ade1654439537555b1c1931e985f214fc36402dc', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-05-30', '16:00', 'EUR', 8.95, NULL, '{"7%": 5.96, "19%": 2.99}', '2026-10-19 16:09:20.057806+02', '7e76b37d2f01b663b74cf786ade1654439537555b1c1931e985f214fc36402dc', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (14, '1b9fa6d2b12a767cc1099b20df1381377c80b143095939d77253c1ce3586b44c', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-05-30', '18:13', 'EUR', 14.94, 0.26, '{"7%": 14.94}', '2026-10-19 16:09:20.094315+02', '1b9fa6d2b12a767cc1099b20df1381377c80b143095939d77253c1ce3586b44c', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (15, 'fad289010aa857c85780ec4620164cbd8b54e3d303bb3d444687833365988e91', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-06-06', '15:39', 'EUR', 18.78, NULL, '{"7%": 17.74, "19%": 1.04}', '2026-10-19 16:09:36.919772+02', 'fad289010aa857c85780ec4620164cbd8b54e3d303bb3d444687833365988e91', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (16, 'adf053d1f6f9bd40e582b84f129d5ad3130ffc1a7f152ddde24ba4192ce4386b', 'made-up', 'Kaufland', 'Testallee 9, 66119 Saarbrücken', '2026-06-07', '16:34', 'EUR', 8.10, NULL, '{"7%": 6.26, "19%": 1.84}', '2026-10-19 16:09:45.613959+02', 'adf053d1f6f9bd40e582b84f129d5ad3130ffc1a7f152ddde24ba4192ce4386b', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (17, '793165c805d15cdf11a9effb721ec57447f3e8b7fa136619e18bf9cb72260119', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-06-08', '19:56', 'EUR', 2.18, NULL, '{"7%": 2.18}', '2026-10-19 16:10:39.414135+02', '793165c805d15cdf11a9effb721ec57447f3e8b7fa136619e18bf9cb72260119', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (7, '0380c1bc1106c0c8312339c47bad7533fdffa486d5897d620f8b49be280b6653', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-05-08', '10:42', 'EUR', 11.97, 0.58, '{"7%": 10.93, "19%": 1.04}', '2026-10-19 16:05:21.725206+02', '0380c1bc1106c0c8312339c47bad7533fdffa486d5897d620f8b49be280b6653', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (8, '1814e7999de88bb0166db6275020faff9ed0e10bb26cd186d5b2832892cef814', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-05-11', '14:56', 'EUR', 8.93, NULL, '{"7%": 8.93}', '2026-10-19 16:05:30.900984+02', '1814e7999de88bb0166db6275020faff9ed0e10bb26cd186d5b2832892cef814', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (9, 'a54314bce3a836bd3c2630fe51d27f2dc82d60e09da77d73770bad22839c6afe', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-05-15', '19:44', 'EUR', 23.65, 0.39, '{"7%": 21.71, "19%": 1.94}', '2026-10-19 16:05:41.16347+02', 'a54314bce3a836bd3c2630fe51d27f2dc82d60e09da77d73770bad22839c6afe', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (10, '8e38aee51f28d68dfdf6761613d110aaff68dba95c9949b199d0400b32044b22', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-05-18', '10:27', 'EUR', 33.14, NULL, '{"7%": 32.24, "19%": 0.9}', '2026-10-19 16:07:45.3698+02', '8e38aee51f28d68dfdf6761613d110aaff68dba95c9949b199d0400b32044b22', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (44, '2ea4e0cbedc796354d27816378153ca7d63e73c87e6c73f6b9c98e127e419909', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-08-31', '15:02', 'EUR', 3.55, NULL, '{"7%": 3.55}', '2026-10-19 16:18:14.407404+02', '2ea4e0cbedc796354d27816378153ca7d63e73c87e6c73f6b9c98e127e419909', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (45, '31422f7165515d916bf624ee457b5b5af06005effc11ae2dd54e95747e44df54', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-09-03', '13:41', 'EUR', 22.61, 0.94, '{"7%": 19.03, "19%": 3.58}', '2026-10-19 16:18:14.458968+02', '31422f7165515d916bf624ee457b5b5af06005effc11ae2dd54e95747e44df54', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (46, '88a6d09409d7f8156632dfc75d47c34bd006de8382ca97c28a2da3f9818197d1', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-09-07', '09:53', 'EUR', 8.00, NULL, '{"7%": 7.11, "19%": 0.89}', '2026-10-19 16:18:50.400884+02', '88a6d09409d7f8156632dfc75d47c34bd006de8382ca97c28a2da3f9818197d1', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (47, 'aec3bf1f93c56ba8e85a2340fc9c4fcf533b48e89ead0467d517766bc366936f', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-09-11', '15:39', 'EUR', 16.38, 0.34, '{"7%": 16.38}', '2026-10-19 16:22:38.880929+02', 'aec3bf1f93c56ba8e85a2340fc9c4fcf533b48e89ead0467d517766bc366936f', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (48, '5b1a80cfd98da0ddbb27476f83ab12cc075eed1ebda624b3e713ddfae0fce425', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-09-16', '14:11', 'EUR', 8.71, NULL, '{"7%": 8.71}', '2026-10-19 16:22:38.928148+02', '5b1a80cfd98da0ddbb27476f83ab12cc075eed1ebda624b3e713ddfae0fce425', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (49, '9c9965f9c34cbcbd69f90d52214b0e38726bdde45c7f98e9567f167f41accd64', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-09-17', '17:19', 'EUR', 11.40, NULL, '{"7%": 13.4, "19%": -2.0}', '2026-10-19 16:22:48.307436+02', '9c9965f9c34cbcbd69f90d52214b0e38726bdde45c7f98e9567f167f41accd64', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (50, 'd9e4c3798b204b3fdfa3068a09603ddac2572e9083b7237401ef64bdba5a995b', 'made-up', 'Kaufland', 'Testallee 9, 66119 Saarbrücken', '2026-09-19', '12:34', 'EUR', 0.55, 0.24, '{"7%": 0.55}', '2026-10-19 16:22:55.402168+02', 'd9e4c3798b204b3fdfa3068a09603ddac2572e9083b7237401ef64bdba5a995b', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (51, '6be738b3f2c37079071e0d1a909be9a551e90b93c66a84358e05b7028c09755a', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-09-21', '18:17', 'EUR', 15.64, NULL, '{"7%": 15.64}', '2026-10-19 16:22:55.448304+02', '6be738b3f2c37079071e0d1a909be9a551e90b93c66a84358e05b7028c09755a', NULL, '2026-10-19 17:36:47.6607+02');
INSERT INTO public.receipts VALUES (52, 'e17c61556d0f8e66fa05e2b778b0a8c9bb3b734ab6d8be1e71700ba770dd157f', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-09-24', '11:31', 'EUR', 13.98, NULL, '{"7%": 13.98}', '2026-10-19 16:22:55.494714+02', 'e17c61556d0f8e66fa05e2b778b0a8c9bb3b734ab6d8be1e71700ba770dd157f', NULL, '2026-10-19 17:36:47.6607+02');


--
-- Data for Name: resolutions; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.resolutions VALUES (1, 'ALDI SÜD', 'Milsani H-Milch 1,5% 1L', 'product', 'p-0001', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (2, 'ALDI SÜD', 'Hähnchenbrustfilet 400g', 'product', 'p-0002', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (3, 'ALDI SÜD', 'Milsani Joghurt Natur 500g', 'product', 'p-0003', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (4, 'GLOBUS', 'Weihenst. Frische Milch 3,5% 1L', 'product', 'p-0004', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (5, 'GLOBUS', 'Kerrygold Butter 250g', 'product', 'p-0005', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (6, 'GLOBUS', 'Rispentomaten', 'product', 'p-0006', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (7, 'GLOBUS', 'Philadelphia Original 175g', 'product', 'p-0007', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (8, 'GLOBUS', 'Coca-Cola 1,5L', 'product', 'p-0008', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (9, 'Lidl', 'Milbona Frische Vollmilch 1L', 'product', 'p-0009', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (10, 'Lidl', 'Barissimo Crema Bohnen 1kg', 'product', 'p-0010', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (11, 'Lidl', 'Pilos Schmand 200g', 'product', 'p-0011', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (12, 'Lidl', 'Freeway Cola 1,5L', 'product', 'p-0012', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (13, 'Lidl', 'Cien Zahncreme 125ml', 'product', 'p-0013', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (14, 'ALDI SÜD', 'Bananen', 'product', 'p-0014', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (15, 'ALDI SÜD', 'Gouda jung Scheiben 400g', 'product', 'p-0015', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (16, 'ALDI SÜD', 'Moser Roth Edel-Vollmilch', 'product', 'p-0016', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (17, 'ALDI SÜD', 'Kokett Toilettenpapier 8x', 'product', 'p-0017', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (18, 'ALDI SÜD', 'Lacura Duschgel 300ml', 'product', 'p-0018', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (19, 'GLOBUS', 'Salatgurke St.', 'product', 'p-0019', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (20, 'GLOBUS', 'Bio Eier Freiland 10St', 'product', 'p-0020', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (21, 'GLOBUS', 'Gerolsteiner Naturell 1,5L', 'product', 'p-0021', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (22, 'GLOBUS', 'Globus Toastbrot Weizen 500g', 'product', 'p-0022', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (23, 'Kaufland', 'Coca-Cola 1,5L', 'product', 'p-0008', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (24, 'GLOBUS', 'Dr.Oetker Ristorante Salame', 'product', 'p-0023', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (25, 'ALDI SÜD', 'Bio Haferflocken 500g', 'product', 'p-0024', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (26, 'GLOBUS', 'Barilla Spaghetti No.5 500g', 'product', 'p-0025', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (27, 'GLOBUS', 'Ja! Haferflocken 500g', 'product', 'p-0026', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (28, 'Kaufland', 'K-Classic Spaghetti 500g', 'product', 'p-0027', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (29, 'GLOBUS', 'Mutti Passata 500g', 'product', 'p-0028', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (30, 'GLOBUS', 'Tempo Taschent. 10x10', 'product', 'p-0029', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (31, 'Kaufland', 'Kerrygold Butter 250g', 'product', 'p-0005', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (32, 'Kaufland', 'Ritter Sport Alpenmilch 100g', 'product', 'p-0030', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (33, 'GLOBUS', 'Nutella 450g', 'product', 'p-0031', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (34, 'GLOBUS', 'Erdbeeren 500g', 'product', 'p-0032', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (35, 'Lidl', 'Nutella 450g', 'product', 'p-0031', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (36, 'GLOBUS', 'Haribo Goldbären 175g', 'product', 'p-0033', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (37, 'Kaufland', 'Barilla Spaghetti No.5 500g', 'product', 'p-0025', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (38, 'Kaufland', 'Mutti Passata 500g', 'product', 'p-0028', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (39, 'Kaufland', 'Frosch Spülmittel Zitrone', 'product', 'p-0034', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (40, 'Lidl', 'Salatgurke', 'product', 'p-0019', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (41, 'ALDI SÜD', 'Cucina Pesto Verde 190g', 'product', 'p-0035', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (42, 'ALDI SÜD', 'Lebkuchen Herzen 500g', 'product', 'p-0036', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (43, 'GLOBUS', 'Avocado Hass St.', 'product', 'p-0037', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (44, 'GLOBUS', 'Lindt Excellence 70% 100g', 'product', 'p-0038', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (45, 'GLOBUS', 'Rinderhackfleisch 500g', 'product', 'p-0039', '{}', NULL, 'identify', '2026-10-19', 'identify v9');
INSERT INTO public.resolutions VALUES (46, 'Lidl', 'Bellarom Espresso Bohnen 1kg', 'product', 'p-0040', '{}', NULL, 'identify', '2026-10-19', 'identify v9');


--
-- Data for Name: sign_ins; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: store_listings; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: uncounted_lines; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Name: checks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.checks_id_seq', 45, true);


--
-- Name: corrections_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.corrections_id_seq', 1, false);


--
-- Name: line_guesses_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.line_guesses_id_seq', 1, false);


--
-- Name: line_resolutions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.line_resolutions_id_seq', 1, false);


--
-- Name: model_calls_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.model_calls_id_seq', 300, true);


--
-- Name: questions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.questions_id_seq', 1, false);


--
-- Name: receipt_lines_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.receipt_lines_id_seq', 395, true);


--
-- Name: receipts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.receipts_id_seq', 60, true);


--
-- Name: resolutions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.resolutions_id_seq', 46, true);


--
-- Name: sign_ins_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.sign_ins_id_seq', 1, false);


--
-- Name: store_listings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.store_listings_id_seq', 1, false);


--
-- Name: uncounted_lines_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.uncounted_lines_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 1, false);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: checks checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checks
    ADD CONSTRAINT checks_pkey PRIMARY KEY (id);


--
-- Name: checks checks_receipt_id_position_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checks
    ADD CONSTRAINT checks_receipt_id_position_key UNIQUE (receipt_id, "position");


--
-- Name: corrections corrections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.corrections
    ADD CONSTRAINT corrections_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: line_guesses line_guesses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.line_guesses
    ADD CONSTRAINT line_guesses_pkey PRIMARY KEY (id);


--
-- Name: line_guesses line_guesses_receipt_id_position_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.line_guesses
    ADD CONSTRAINT line_guesses_receipt_id_position_key UNIQUE (receipt_id, "position");


--
-- Name: line_resolutions line_resolutions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.line_resolutions
    ADD CONSTRAINT line_resolutions_pkey PRIMARY KEY (id);


--
-- Name: line_resolutions line_resolutions_receipt_id_position_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.line_resolutions
    ADD CONSTRAINT line_resolutions_receipt_id_position_key UNIQUE (receipt_id, "position");


--
-- Name: model_calls model_calls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_calls
    ADD CONSTRAINT model_calls_pkey PRIMARY KEY (id);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: questions questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questions
    ADD CONSTRAINT questions_pkey PRIMARY KEY (id);


--
-- Name: questions questions_receipt_id_position_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questions
    ADD CONSTRAINT questions_receipt_id_position_key UNIQUE (receipt_id, "position");


--
-- Name: receipt_lines receipt_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipt_lines
    ADD CONSTRAINT receipt_lines_pkey PRIMARY KEY (id);


--
-- Name: receipt_lines receipt_lines_receipt_id_position_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipt_lines
    ADD CONSTRAINT receipt_lines_receipt_id_position_key UNIQUE (receipt_id, "position");


--
-- Name: receipts receipts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipts
    ADD CONSTRAINT receipts_pkey PRIMARY KEY (id);


--
-- Name: receipts receipts_source_image_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipts
    ADD CONSTRAINT receipts_source_image_key UNIQUE (source_image);


--
-- Name: resolutions resolutions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resolutions
    ADD CONSTRAINT resolutions_pkey PRIMARY KEY (id);


--
-- Name: resolutions resolutions_store_raw_name_line_type_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resolutions
    ADD CONSTRAINT resolutions_store_raw_name_line_type_key UNIQUE (store, raw_name, line_type);


--
-- Name: sign_ins sign_ins_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sign_ins
    ADD CONSTRAINT sign_ins_pkey PRIMARY KEY (id);


--
-- Name: sign_ins sign_ins_token_sha256_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sign_ins
    ADD CONSTRAINT sign_ins_token_sha256_key UNIQUE (token_sha256);


--
-- Name: store_listings store_listings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_listings
    ADD CONSTRAINT store_listings_pkey PRIMARY KEY (id);


--
-- Name: store_listings store_listings_store_article_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_listings
    ADD CONSTRAINT store_listings_store_article_number_key UNIQUE (store, article_number);


--
-- Name: uncounted_lines uncounted_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.uncounted_lines
    ADD CONSTRAINT uncounted_lines_pkey PRIMARY KEY (id);


--
-- Name: uncounted_lines uncounted_lines_receipt_id_position_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.uncounted_lines
    ADD CONSTRAINT uncounted_lines_receipt_id_position_key UNIQUE (receipt_id, "position");


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_name_key UNIQUE (name);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_token_sha256_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_token_sha256_key UNIQUE (token_sha256);


--
-- Name: ix_jobs_image_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_image_sha256 ON public.jobs USING btree (image_sha256);


--
-- Name: ix_jobs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_user_id ON public.jobs USING btree (user_id);


--
-- Name: ix_model_calls_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_calls_at ON public.model_calls USING btree (at);


--
-- Name: ix_model_calls_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_calls_job_id ON public.model_calls USING btree (job_id);


--
-- Name: ix_receipts_image_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_receipts_image_sha256 ON public.receipts USING btree (image_sha256);


--
-- Name: ix_receipts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_receipts_user_id ON public.receipts USING btree (user_id);


--
-- Name: ix_sign_ins_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sign_ins_user_id ON public.sign_ins USING btree (user_id);


--
-- Name: checks checks_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checks
    ADD CONSTRAINT checks_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.receipts(id) ON DELETE CASCADE;


--
-- Name: corrections corrections_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.corrections
    ADD CONSTRAINT corrections_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.receipts(id) ON DELETE SET NULL;


--
-- Name: jobs jobs_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.receipts(id) ON DELETE SET NULL;


--
-- Name: jobs jobs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: line_guesses line_guesses_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.line_guesses
    ADD CONSTRAINT line_guesses_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.receipts(id) ON DELETE CASCADE;


--
-- Name: line_resolutions line_resolutions_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.line_resolutions
    ADD CONSTRAINT line_resolutions_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: line_resolutions line_resolutions_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.line_resolutions
    ADD CONSTRAINT line_resolutions_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.receipts(id) ON DELETE CASCADE;


--
-- Name: model_calls model_calls_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_calls
    ADD CONSTRAINT model_calls_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE SET NULL;


--
-- Name: questions questions_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questions
    ADD CONSTRAINT questions_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.receipts(id) ON DELETE CASCADE;


--
-- Name: receipt_lines receipt_lines_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipt_lines
    ADD CONSTRAINT receipt_lines_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.receipts(id) ON DELETE CASCADE;


--
-- Name: receipts receipts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipts
    ADD CONSTRAINT receipts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: resolutions resolutions_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resolutions
    ADD CONSTRAINT resolutions_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: sign_ins sign_ins_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sign_ins
    ADD CONSTRAINT sign_ins_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: store_listings store_listings_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_listings
    ADD CONSTRAINT store_listings_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: uncounted_lines uncounted_lines_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.uncounted_lines
    ADD CONSTRAINT uncounted_lines_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.receipts(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict ybgGxhs9wcBbanAIyG9ExSXhcJLydM5wJgZ3PqoLwgw1s0Jw7OgxpHq70S1d4wi

