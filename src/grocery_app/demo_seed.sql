--
-- PostgreSQL database dump
--

\restrict qFx5eKZanRqMG9ij01yKV9Thm4RlhkhxJpzfU28Hajg25adr5PImAEw4IDkYRb8

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
    shopper_product_id character varying NOT NULL,
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
    dev_seen_at timestamp with time zone
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
    product_id character varying NOT NULL,
    confirmed_by character varying,
    confirmed_at date,
    basis character varying,
    shopper_words character varying,
    memory_before jsonb,
    disagrees_with character varying
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
    user_id integer
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
    created_at timestamp with time zone DEFAULT now() NOT NULL
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

INSERT INTO public.alembic_version VALUES ('0018');


--
-- Data for Name: checks; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.checks VALUES (1, 1, 8, 'Dr.Oetker Ristorante Salame', 'p-0008', '2026-10-12 14:20:48.466681+02');
INSERT INTO public.checks VALUES (2, 1, 9, 'Mutti Passata 500g', 'p-0009', '2026-10-12 14:20:48.466681+02');
INSERT INTO public.checks VALUES (3, 2, 2, 'Bananen', 'p-0006', '2026-10-12 14:27:44.218982+02');
INSERT INTO public.checks VALUES (4, 3, 3, 'Dr.Oetker Ristorante Salame', 'p-0008', '2026-10-12 14:28:31.218386+02');
INSERT INTO public.checks VALUES (5, 5, 1, 'Bananen', 'p-0006', '2026-10-12 14:32:24.906035+02');
INSERT INTO public.checks VALUES (6, 7, 5, 'Gerolsteiner Naturell 1,5L', 'p-0022', '2026-10-12 14:40:16.684166+02');
INSERT INTO public.checks VALUES (7, 7, 7, 'Philadelphia Original 175g', 'p-0023', '2026-10-12 14:40:16.684166+02');
INSERT INTO public.checks VALUES (8, 8, 4, 'Philadelphia Original 175g', 'p-0023', '2026-10-12 14:40:16.741641+02');
INSERT INTO public.checks VALUES (9, 9, 2, 'Bananen', 'p-0006', '2026-10-12 14:41:03.765454+02');
INSERT INTO public.checks VALUES (10, 10, 4, 'Philadelphia Original 175g', 'p-0023', '2026-10-12 14:41:03.834304+02');


--
-- Data for Name: corrections; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: jobs; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.jobs VALUES ('505bb0a9-434e-4f4d-9c3e-886394e6b899', 'done', '6501ba0bff41f081f734af3737680a6ac646d14daf33987fc8b27b5209f662cb', '2026-06-21-globus.jpg', 1, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:12:37.468199+02', '2026-10-12 14:12:37.471523+02', '2026-10-12 14:20:48.489567+02', false, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('68d4aad9-c1fb-4c54-a2da-fd8db7b26175', 'done', '27240d4b650bf58b65f8f53fa5e669d2158a60165706b410abc794790493a892', '2026-10-10-aldi-sued.jpg', 9, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:40:16.767782+02', '2026-10-12 14:40:16.769479+02', '2026-10-12 14:41:03.784092+02', false, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('a53a06e4-8295-4478-8e99-f04aa0f96ade', 'done', 'f6d822434fc129ea2a692964fb69360a22aa15540d9be35a8919aaffebf49461', '2026-06-27-aldi-sued.jpg', 2, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:20:48.524938+02', '2026-10-12 14:20:48.527323+02', '2026-10-12 14:27:44.250572+02', false, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('af3dfa5a-7ff0-4f6a-828b-6b080b639773', 'done', 'e3377b57e73c8e41c3ffd43ec5c3a8fec37aebcda0c63b9ecc5ad7df814f0028', '2026-07-04-globus.jpg', 3, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:27:44.287456+02', '2026-10-12 14:27:44.290337+02', '2026-10-12 14:28:31.237881+02', false, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('b41f65d5-f2da-444c-87a7-d49d8b9a6644', 'done', 'e60b676b22e46af55d670adc220ba38167ca2feb24873f729b27acb0b1f60011', '2026-10-10-globus.jpg', 10, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:41:03.807257+02', '2026-10-12 14:41:03.809713+02', '2026-10-12 14:41:03.842459+02', false, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'done', 'a7727d8c4459ceabc7e3bf88d80341f54bb61949453e454471359a4fac18e63f', '2026-07-04-lidl.jpg', 4, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:28:31.26455+02', '2026-10-12 14:28:31.26636+02', '2026-10-12 14:29:51.933917+02', false, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('ac205ce1-a0dc-4192-bdae-7e3d9c94929e', 'done', 'eff65a36244342973ff76be0f3d146394f10a9d776c95d7bafeaa7e335d491f6', '2026-07-15-aldi-sued.jpg', 5, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:31:32.545452+02', '2026-10-12 14:31:32.549144+02', '2026-10-12 14:32:24.937116+02', false, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'done', '93d59e809840916984cd9374e555e1b60b2cb5e5be6ed8a9b5a504bbe6143668', '2026-07-18-kaufland.jpg', 6, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:32:24.974634+02', '2026-10-12 14:32:24.976966+02', '2026-10-12 14:38:06.01713+02', false, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('aab74218-18ae-45ab-9a30-a118bc4eb422', 'done', '8f8a6007d4a0cdb156b0b395977fddf1368f739bcba10e040535a45537d61845', '2026-08-28-globus.jpg', 7, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:38:06.130078+02', '2026-10-12 14:38:06.133557+02', '2026-10-12 14:40:16.703492+02', false, NULL, NULL, NULL);
INSERT INTO public.jobs VALUES ('30754434-1ad5-4bc8-b664-30e0bafe7f21', 'done', '94aab3e2bc34e5b4f753d8f4076e9669bfc251b88495c1dcda556cce66848eee', '2026-09-14-globus.jpg', 8, 'made-up', 'demo', NULL, NULL, 0.00000, NULL, '2026-10-12 14:40:16.724971+02', '2026-10-12 14:40:16.726549+02', '2026-10-12 14:40:16.748347+02', false, NULL, NULL, NULL);


--
-- Data for Name: line_guesses; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: line_resolutions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: model_calls; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.model_calls VALUES (1, '2026-10-12 14:12:43.803444+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 738, 256, 0, 0.00151);
INSERT INTO public.model_calls VALUES (2, '2026-10-12 14:12:47.748521+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4475, 368, 0, 0.00474);
INSERT INTO public.model_calls VALUES (3, '2026-10-12 14:13:02.384566+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 340, 1031, 5, 0.07412);
INSERT INTO public.model_calls VALUES (4, '2026-10-12 14:13:20.176625+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 515, 651, 0, 0.00283);
INSERT INTO public.model_calls VALUES (5, '2026-10-12 14:13:23.855119+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4863, 332, 0, 0.00489);
INSERT INTO public.model_calls VALUES (6, '2026-10-12 14:13:35.172844+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 654, 414, 0, 0.00204);
INSERT INTO public.model_calls VALUES (7, '2026-10-12 14:13:38.937967+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4395, 306, 0, 0.00444);
INSERT INTO public.model_calls VALUES (8, '2026-10-12 14:13:58.03282+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 333, 1050, 11, 0.15819);
INSERT INTO public.model_calls VALUES (9, '2026-10-12 14:14:06.09516+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 526, 1205, 0, 0.00491);
INSERT INTO public.model_calls VALUES (10, '2026-10-12 14:14:08.933374+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4785, 287, 0, 0.00466);
INSERT INTO public.model_calls VALUES (11, '2026-10-12 14:14:14.082249+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 834, 388, 0, 0.00208);
INSERT INTO public.model_calls VALUES (12, '2026-10-12 14:14:17.86618+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4513, 356, 0, 0.00472);
INSERT INTO public.model_calls VALUES (13, '2026-10-12 14:14:43.22236+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 336, 1781, 7, 0.10493);
INSERT INTO public.model_calls VALUES (14, '2026-10-12 14:14:52.074487+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 532, 1161, 0, 0.00475);
INSERT INTO public.model_calls VALUES (15, '2026-10-12 14:14:57.506909+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4922, 502, 0, 0.00557);
INSERT INTO public.model_calls VALUES (16, '2026-10-12 14:15:03.731303+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 603, 126, 0, 0.00092);
INSERT INTO public.model_calls VALUES (17, '2026-10-12 14:15:07.715797+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4319, 347, 0, 0.00454);
INSERT INTO public.model_calls VALUES (18, '2026-10-12 14:15:22.333422+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 334, 1436, 7, 0.10364);
INSERT INTO public.model_calls VALUES (19, '2026-10-12 14:15:27.946991+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 629, 993, 0, 0.00420);
INSERT INTO public.model_calls VALUES (20, '2026-10-12 14:15:47.499001+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4751, 2512, 0, 0.01298);
INSERT INTO public.model_calls VALUES (21, '2026-10-12 14:15:52.323219+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 906, 245, 0, 0.00160);
INSERT INTO public.model_calls VALUES (22, '2026-10-12 14:15:55.72997+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4540, 328, 0, 0.00464);
INSERT INTO public.model_calls VALUES (23, '2026-10-12 14:16:37.332626+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 336, 1672, 23, 0.32852);
INSERT INTO public.model_calls VALUES (24, '2026-10-12 14:16:45.819428+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 536, 733, 0, 0.00315);
INSERT INTO public.model_calls VALUES (25, '2026-10-12 14:16:51.494068+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 5196, 358, 0, 0.00524);
INSERT INTO public.model_calls VALUES (26, '2026-10-12 14:16:59.32552+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 772, 536, 0, 0.00259);
INSERT INTO public.model_calls VALUES (27, '2026-10-12 14:17:05.091066+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4419, 216, 0, 0.00412);
INSERT INTO public.model_calls VALUES (28, '2026-10-12 14:17:25.589213+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 328, 1001, 9, 0.13000);
INSERT INTO public.model_calls VALUES (29, '2026-10-12 14:17:34.279749+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 438, 961, 0, 0.00393);
INSERT INTO public.model_calls VALUES (30, '2026-10-12 14:17:38.12052+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4708, 224, 0, 0.00437);
INSERT INTO public.model_calls VALUES (31, '2026-10-12 14:17:43.371894+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 878, 318, 0, 0.00185);
INSERT INTO public.model_calls VALUES (32, '2026-10-12 14:17:49.17388+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4498, 514, 0, 0.00530);
INSERT INTO public.model_calls VALUES (33, '2026-10-12 14:18:29.884769+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 330, 1256, 13, 0.18696);
INSERT INTO public.model_calls VALUES (34, '2026-10-12 14:18:37.699989+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 433, 153, 0, 0.00090);
INSERT INTO public.model_calls VALUES (35, '2026-10-12 14:18:42.676897+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4819, 266, 0, 0.00461);
INSERT INTO public.model_calls VALUES (36, '2026-10-12 14:18:48.898328+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 807, 446, 0, 0.00228);
INSERT INTO public.model_calls VALUES (37, '2026-10-12 14:18:58.152191+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4457, 1091, 0, 0.00743);
INSERT INTO public.model_calls VALUES (38, '2026-10-12 14:19:43.714954+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 335, 1360, 6, 0.08935);
INSERT INTO public.model_calls VALUES (39, '2026-10-12 14:19:45.864084+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 479, 271, 0, 0.00138);
INSERT INTO public.model_calls VALUES (40, '2026-10-12 14:20:01.021001+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4838, 1886, 0, 0.01070);
INSERT INTO public.model_calls VALUES (41, '2026-10-12 14:20:05.731348+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 670, 316, 0, 0.00169);
INSERT INTO public.model_calls VALUES (42, '2026-10-12 14:20:12.253379+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4341, 585, 0, 0.00545);
INSERT INTO public.model_calls VALUES (43, '2026-10-12 14:20:34.884562+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 334, 1167, 19, 0.27063);
INSERT INTO public.model_calls VALUES (44, '2026-10-12 14:20:41.746998+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 488, 943, 0, 0.00390);
INSERT INTO public.model_calls VALUES (45, '2026-10-12 14:20:48.455468+02', 'finding', '505bb0a9-434e-4f4d-9c3e-886394e6b899', 'gemini-3.8-flash', 4863, 648, 0, 0.00608);
INSERT INTO public.model_calls VALUES (46, '2026-10-12 14:20:52.101966+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 905, 287, 0, 0.00176);
INSERT INTO public.model_calls VALUES (47, '2026-10-12 14:20:56.293763+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4530, 370, 0, 0.00479);
INSERT INTO public.model_calls VALUES (48, '2026-10-12 14:21:07.098879+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 343, 1009, 2, 0.03204);
INSERT INTO public.model_calls VALUES (49, '2026-10-12 14:21:12.016345+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 523, 603, 0, 0.00265);
INSERT INTO public.model_calls VALUES (50, '2026-10-12 14:21:15.803125+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4859, 401, 0, 0.00515);
INSERT INTO public.model_calls VALUES (51, '2026-10-12 14:21:20.092035+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 916, 272, 0, 0.00171);
INSERT INTO public.model_calls VALUES (52, '2026-10-12 14:21:24.602548+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4542, 328, 0, 0.00464);
INSERT INTO public.model_calls VALUES (53, '2026-10-12 14:22:03.461646+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 338, 1297, 9, 0.13112);
INSERT INTO public.model_calls VALUES (54, '2026-10-12 14:22:11.682119+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 475, 1123, 0, 0.00457);
INSERT INTO public.model_calls VALUES (55, '2026-10-12 14:22:16.047088+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4950, 280, 0, 0.00476);
INSERT INTO public.model_calls VALUES (56, '2026-10-12 14:22:18.623582+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 937, 262, 0, 0.00169);
INSERT INTO public.model_calls VALUES (57, '2026-10-12 14:22:23.05032+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4563, 284, 0, 0.00449);
INSERT INTO public.model_calls VALUES (58, '2026-10-12 14:22:47.461272+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 340, 1171, 8, 0.11665);
INSERT INTO public.model_calls VALUES (59, '2026-10-12 14:22:51.408559+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 513, 250, 0, 0.00132);
INSERT INTO public.model_calls VALUES (60, '2026-10-12 14:22:54.942965+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 5071, 346, 0, 0.00510);
INSERT INTO public.model_calls VALUES (61, '2026-10-12 14:22:59.137267+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 898, 355, 0, 0.00200);
INSERT INTO public.model_calls VALUES (62, '2026-10-12 14:23:05.338191+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4520, 538, 0, 0.00541);
INSERT INTO public.model_calls VALUES (63, '2026-10-12 14:23:38.718359+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 338, 1019, 9, 0.13007);
INSERT INTO public.model_calls VALUES (64, '2026-10-12 14:23:42.646263+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 453, 480, 0, 0.00214);
INSERT INTO public.model_calls VALUES (65, '2026-10-12 14:23:55.654755+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4874, 510, 0, 0.00557);
INSERT INTO public.model_calls VALUES (66, '2026-10-12 14:23:59.292123+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 911, 346, 0, 0.00198);
INSERT INTO public.model_calls VALUES (67, '2026-10-12 14:24:03.979285+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4540, 525, 0, 0.00537);
INSERT INTO public.model_calls VALUES (68, '2026-10-12 14:24:25.134862+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 338, 1315, 11, 0.15918);
INSERT INTO public.model_calls VALUES (69, '2026-10-12 14:24:28.519433+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 543, 273, 0, 0.00143);
INSERT INTO public.model_calls VALUES (70, '2026-10-12 14:24:36.630586+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 5042, 565, 0, 0.00590);
INSERT INTO public.model_calls VALUES (71, '2026-10-12 14:24:41.87028+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 959, 517, 0, 0.00266);
INSERT INTO public.model_calls VALUES (72, '2026-10-12 14:24:54.825992+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4581, 1409, 0, 0.00872);
INSERT INTO public.model_calls VALUES (73, '2026-10-12 14:25:11.629618+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 336, 1488, 7, 0.10383);
INSERT INTO public.model_calls VALUES (74, '2026-10-12 14:25:18.991678+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 538, 974, 0, 0.00406);
INSERT INTO public.model_calls VALUES (75, '2026-10-12 14:25:33.143417+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 5003, 1855, 0, 0.01071);
INSERT INTO public.model_calls VALUES (76, '2026-10-12 14:25:36.053564+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 893, 262, 0, 0.00165);
INSERT INTO public.model_calls VALUES (78, '2026-10-12 14:26:29.235473+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 346, 1552, 16, 0.23008);
INSERT INTO public.model_calls VALUES (80, '2026-10-12 14:26:36.096661+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 5124, 433, 0, 0.00547);
INSERT INTO public.model_calls VALUES (81, '2026-10-12 14:27:06.288171+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 910, 3538, 0, 0.01395);
INSERT INTO public.model_calls VALUES (83, '2026-10-12 14:27:28.468524+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 972, 1466, 0, 0.00623);
INSERT INTO public.model_calls VALUES (91, '2026-10-12 14:28:34.536399+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 640, 186, 0, 0.00118);
INSERT INTO public.model_calls VALUES (92, '2026-10-12 14:28:40.299911+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 4270, 387, 0, 0.00465);
INSERT INTO public.model_calls VALUES (93, '2026-10-12 14:28:43.804142+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 623, 139, 0, 0.00099);
INSERT INTO public.model_calls VALUES (94, '2026-10-12 14:28:50.852373+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 4266, 768, 0, 0.00608);
INSERT INTO public.model_calls VALUES (95, '2026-10-12 14:28:55.886289+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 619, 152, 0, 0.00103);
INSERT INTO public.model_calls VALUES (96, '2026-10-12 14:29:06.205526+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 4267, 443, 0, 0.00486);
INSERT INTO public.model_calls VALUES (97, '2026-10-12 14:29:09.130101+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 624, 145, 0, 0.00101);
INSERT INTO public.model_calls VALUES (98, '2026-10-12 14:29:22.885212+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 4271, 305, 0, 0.00435);
INSERT INTO public.model_calls VALUES (99, '2026-10-12 14:29:26.581919+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 636, 205, 0, 0.00125);
INSERT INTO public.model_calls VALUES (100, '2026-10-12 14:29:31.388752+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 4273, 341, 0, 0.00448);
INSERT INTO public.model_calls VALUES (77, '2026-10-12 14:25:44.149549+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4528, 330, 0, 0.00463);
INSERT INTO public.model_calls VALUES (79, '2026-10-12 14:26:32.354324+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 551, 287, 0, 0.00149);
INSERT INTO public.model_calls VALUES (82, '2026-10-12 14:27:10.832215+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4545, 304, 0, 0.00455);
INSERT INTO public.model_calls VALUES (84, '2026-10-12 14:27:44.211686+02', 'finding', 'a53a06e4-8295-4478-8e99-f04aa0f96ade', 'gemini-3.8-flash', 4596, 465, 0, 0.00519);
INSERT INTO public.model_calls VALUES (85, '2026-10-12 14:27:48.91539+02', 'finding', 'af3dfa5a-7ff0-4f6a-828b-6b080b639773', 'gemini-3.8-flash', 734, 184, 0, 0.00124);
INSERT INTO public.model_calls VALUES (86, '2026-10-12 14:27:52.706039+02', 'finding', 'af3dfa5a-7ff0-4f6a-828b-6b080b639773', 'gemini-3.8-flash', 4371, 365, 0, 0.00465);
INSERT INTO public.model_calls VALUES (87, '2026-10-12 14:28:04.653879+02', 'finding', 'af3dfa5a-7ff0-4f6a-828b-6b080b639773', 'gemini-3.8-flash', 888, 285, 0, 0.00173);
INSERT INTO public.model_calls VALUES (88, '2026-10-12 14:28:10.219448+02', 'finding', 'af3dfa5a-7ff0-4f6a-828b-6b080b639773', 'gemini-3.8-flash', 4487, 252, 0, 0.00431);
INSERT INTO public.model_calls VALUES (89, '2026-10-12 14:28:15.21533+02', 'finding', 'af3dfa5a-7ff0-4f6a-828b-6b080b639773', 'gemini-3.8-flash', 717, 163, 0, 0.00115);
INSERT INTO public.model_calls VALUES (90, '2026-10-12 14:28:31.21074+02', 'finding', 'af3dfa5a-7ff0-4f6a-828b-6b080b639773', 'gemini-3.8-flash', 4357, 2234, 0, 0.01165);
INSERT INTO public.model_calls VALUES (101, '2026-10-12 14:29:33.542462+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 620, 124, 0, 0.00093);
INSERT INTO public.model_calls VALUES (102, '2026-10-12 14:29:51.9031+02', 'finding', 'bf07206a-ce54-409e-8a0b-7d4cb642b8bd', 'gemini-3.8-flash', 4267, 233, 0, 0.00407);
INSERT INTO public.model_calls VALUES (103, '2026-10-12 14:31:38.568174+02', 'finding', 'ac205ce1-a0dc-4192-bdae-7e3d9c94929e', 'gemini-3.8-flash', 4536, 413, 0, 0.00495);
INSERT INTO public.model_calls VALUES (104, '2026-10-12 14:32:01.295297+02', 'finding', 'ac205ce1-a0dc-4192-bdae-7e3d9c94929e', 'gemini-3.8-flash', 340, 906, 3, 0.04565);
INSERT INTO public.model_calls VALUES (105, '2026-10-12 14:32:06.990628+02', 'finding', 'ac205ce1-a0dc-4192-bdae-7e3d9c94929e', 'gemini-3.8-flash', 489, 552, 0, 0.00244);
INSERT INTO public.model_calls VALUES (106, '2026-10-12 14:32:24.886291+02', 'finding', 'ac205ce1-a0dc-4192-bdae-7e3d9c94929e', 'gemini-3.8-flash', 4856, 706, 0, 0.00629);
INSERT INTO public.model_calls VALUES (107, '2026-10-12 14:32:27.59661+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 628, 133, 0, 0.00097);
INSERT INTO public.model_calls VALUES (108, '2026-10-12 14:32:31.066269+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4258, 304, 0, 0.00433);
INSERT INTO public.model_calls VALUES (109, '2026-10-12 14:32:42.642708+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 335, 684, 5, 0.07282);
INSERT INTO public.model_calls VALUES (110, '2026-10-12 14:32:48.889286+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 505, 694, 0, 0.00298);
INSERT INTO public.model_calls VALUES (111, '2026-10-12 14:32:52.931221+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4583, 347, 0, 0.00474);
INSERT INTO public.model_calls VALUES (112, '2026-10-12 14:32:54.890166+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 626, 82, 0, 0.00078);
INSERT INTO public.model_calls VALUES (113, '2026-10-12 14:33:00.334435+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4259, 253, 0, 0.00414);
INSERT INTO public.model_calls VALUES (114, '2026-10-12 14:34:11.973457+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 334, 1382, 9, 0.13143);
INSERT INTO public.model_calls VALUES (115, '2026-10-12 14:35:26.066771+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 334, 1350, 8, 0.11731);
INSERT INTO public.model_calls VALUES (116, '2026-10-12 14:35:28.967055+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 503, 248, 0, 0.00131);
INSERT INTO public.model_calls VALUES (117, '2026-10-12 14:35:32.966246+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4618, 273, 0, 0.00449);
INSERT INTO public.model_calls VALUES (118, '2026-10-12 14:35:35.188775+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 651, 156, 0, 0.00107);
INSERT INTO public.model_calls VALUES (119, '2026-10-12 14:35:59.687589+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4270, 2337, 0, 0.01197);
INSERT INTO public.model_calls VALUES (120, '2026-10-12 14:36:23.178221+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 343, 1267, 3, 0.04701);
INSERT INTO public.model_calls VALUES (121, '2026-10-12 14:36:29.127981+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 505, 254, 0, 0.00133);
INSERT INTO public.model_calls VALUES (122, '2026-10-12 14:36:40.138141+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4572, 1507, 0, 0.00908);
INSERT INTO public.model_calls VALUES (123, '2026-10-12 14:36:43.660668+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 644, 84, 0, 0.00080);
INSERT INTO public.model_calls VALUES (124, '2026-10-12 14:36:57.198372+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4268, 1939, 0, 0.01047);
INSERT INTO public.model_calls VALUES (125, '2026-10-12 14:37:24.181173+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 335, 1466, 13, 0.18775);
INSERT INTO public.model_calls VALUES (126, '2026-10-12 14:37:31.228405+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 566, 688, 0, 0.00300);
INSERT INTO public.model_calls VALUES (127, '2026-10-12 14:37:34.13955+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4770, 267, 0, 0.00458);
INSERT INTO public.model_calls VALUES (128, '2026-10-12 14:37:36.844124+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 647, 155, 0, 0.00107);
INSERT INTO public.model_calls VALUES (129, '2026-10-12 14:37:41.476893+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4265, 297, 0, 0.00431);
INSERT INTO public.model_calls VALUES (130, '2026-10-12 14:37:54.760792+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 336, 825, 5, 0.07335);
INSERT INTO public.model_calls VALUES (131, '2026-10-12 14:38:02.297941+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 559, 1042, 0, 0.00433);
INSERT INTO public.model_calls VALUES (132, '2026-10-12 14:38:05.980192+02', 'finding', '5d15fd1a-19d9-4c1a-aa88-0ccd01454081', 'gemini-3.8-flash', 4595, 369, 0, 0.00483);
INSERT INTO public.model_calls VALUES (133, '2026-10-12 14:38:08.399721+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 730, 149, 0, 0.00111);
INSERT INTO public.model_calls VALUES (134, '2026-10-12 14:38:12.415224+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 4362, 362, 0, 0.00463);
INSERT INTO public.model_calls VALUES (135, '2026-10-12 14:38:26.732831+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 343, 1152, 5, 0.07458);
INSERT INTO public.model_calls VALUES (136, '2026-10-12 14:38:34.711174+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 524, 1004, 0, 0.00416);
INSERT INTO public.model_calls VALUES (137, '2026-10-12 14:38:38.113441+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 4690, 308, 0, 0.00467);
INSERT INTO public.model_calls VALUES (138, '2026-10-12 14:38:41.247668+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 741, 219, 0, 0.00138);
INSERT INTO public.model_calls VALUES (139, '2026-10-12 14:38:45.445483+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 4345, 406, 0, 0.00478);
INSERT INTO public.model_calls VALUES (140, '2026-10-12 14:39:04.667229+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 336, 915, 9, 0.12968);
INSERT INTO public.model_calls VALUES (141, '2026-10-12 14:39:11.130463+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 440, 1044, 0, 0.00425);
INSERT INTO public.model_calls VALUES (142, '2026-10-12 14:39:16.234688+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 4707, 408, 0, 0.00506);
INSERT INTO public.model_calls VALUES (143, '2026-10-12 14:39:19.264982+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 902, 171, 0, 0.00132);
INSERT INTO public.model_calls VALUES (144, '2026-10-12 14:39:25.859227+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 4475, 809, 0, 0.00639);
INSERT INTO public.model_calls VALUES (145, '2026-10-12 14:40:01.634724+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 332, 793, 7, 0.10122);
INSERT INTO public.model_calls VALUES (146, '2026-10-12 14:40:06.857778+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 460, 209, 0, 0.00113);
INSERT INTO public.model_calls VALUES (147, '2026-10-12 14:40:16.674976+02', 'finding', 'aab74218-18ae-45ab-9a30-a118bc4eb422', 'gemini-3.8-flash', 4715, 1127, 0, 0.00776);
INSERT INTO public.model_calls VALUES (148, '2026-10-12 14:40:29.768428+02', 'finding', '68d4aad9-c1fb-4c54-a2da-fd8db7b26175', 'gemini-3.8-flash', 920, 1665, 0, 0.00693);
INSERT INTO public.model_calls VALUES (149, '2026-10-12 14:40:33.240535+02', 'finding', '68d4aad9-c1fb-4c54-a2da-fd8db7b26175', 'gemini-3.8-flash', 4544, 327, 0, 0.00463);
INSERT INTO public.model_calls VALUES (150, '2026-10-12 14:40:57.036257+02', 'finding', '68d4aad9-c1fb-4c54-a2da-fd8db7b26175', 'gemini-3.8-flash', 338, 1918, 13, 0.18945);
INSERT INTO public.model_calls VALUES (151, '2026-10-12 14:41:00.388778+02', 'finding', '68d4aad9-c1fb-4c54-a2da-fd8db7b26175', 'gemini-3.8-flash', 572, 316, 0, 0.00161);
INSERT INTO public.model_calls VALUES (152, '2026-10-12 14:41:03.756216+02', 'finding', '68d4aad9-c1fb-4c54-a2da-fd8db7b26175', 'gemini-3.8-flash', 5179, 317, 0, 0.00507);
INSERT INTO public.model_calls VALUES (153, '2026-10-12 14:42:50.278192+02', 'other', NULL, 'gemini-3.8-flash', 61, 1028, 16, 0.22790);
INSERT INTO public.model_calls VALUES (154, '2026-10-12 14:44:36.702293+02', 'other', NULL, 'gemini-3.8-flash', 56, 854, 9, 0.12924);
INSERT INTO public.model_calls VALUES (155, '2026-10-12 14:45:05.622232+02', 'other', NULL, 'gemini-3.8-flash', 57, 1512, 12, 0.17371);
INSERT INTO public.model_calls VALUES (156, '2026-10-12 14:46:52.491094+02', 'other', NULL, 'gemini-3.8-flash', 55, 858, 8, 0.11526);
INSERT INTO public.model_calls VALUES (157, '2026-10-12 14:51:44.604315+02', 'other', NULL, 'gemini-3.8-flash', 56, 874, 2, 0.03132);
INSERT INTO public.model_calls VALUES (158, '2026-10-12 14:52:44.279379+02', 'other', NULL, 'gemini-3.8-flash', 54, 1313, 20, 0.28496);
INSERT INTO public.model_calls VALUES (159, '2026-10-12 14:53:13.107348+02', 'other', NULL, 'gemini-3.8-flash', 54, 1470, 5, 0.07555);
INSERT INTO public.model_calls VALUES (160, '2026-10-12 14:54:04.848376+02', 'other', NULL, 'gemini-3.8-flash', 62, 2243, 34, 0.48446);
INSERT INTO public.model_calls VALUES (161, '2026-10-12 14:55:03.507788+02', 'other', NULL, 'gemini-3.8-flash', 60, 2023, 30, 0.42763);
INSERT INTO public.model_calls VALUES (162, '2026-10-12 14:55:50.385471+02', 'other', NULL, 'gemini-3.8-flash', 55, 1734, 13, 0.18854);
INSERT INTO public.model_calls VALUES (163, '2026-10-12 14:56:09.338838+02', 'other', NULL, 'gemini-3.8-flash', 57, 1108, 4, 0.06020);
INSERT INTO public.model_calls VALUES (164, '2026-10-12 14:56:45.966889+02', 'other', NULL, 'gemini-3.8-flash', 54, 1612, 14, 0.20209);
INSERT INTO public.model_calls VALUES (165, '2026-10-12 14:57:08.148288+02', 'other', NULL, 'gemini-3.8-flash', 57, 683, 11, 0.15660);
INSERT INTO public.model_calls VALUES (166, '2026-10-12 14:57:20.753726+02', 'other', NULL, 'gemini-3.8-flash', 59, 955, 4, 0.05963);
INSERT INTO public.model_calls VALUES (167, '2026-10-12 14:58:11.504154+02', 'other', NULL, 'gemini-3.8-flash', 57, 869, 15, 0.21330);


--
-- Data for Name: products; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.products VALUES ('p-0006', 'Bananen', 'Bananen', NULL, '{"unit": null, "count": 1, "value": null}', 'bananen', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{lose}', NULL, '2026-10-12 14:41:03.927921+02');
INSERT INTO public.products VALUES ('p-0008', 'Pizza Salami', 'Pizza Salami', 'Dr. Oetker', '{"unit": null, "count": 1, "value": null}', 'pizza', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Ristorante}', '{"file": "e017ac5a82f1a05c6a309667c22798a18f872bc93fc8a3dfe29a3703f4f9cf77", "from": "dutchshopper.com", "page": "https://dutchshopper.com/en/products/dr-oetker-ristorante-pizza-salame", "source": "https://dutchshopper.com/cdn/shop/files/648181_b37f7f3d-2c71-406a-b643-833d5d9be7a6.png?v=1791789046&width=2500"}', '2026-10-12 14:42:58.779172+02');
INSERT INTO public.products VALUES ('p-0022', 'Mineralwasser', 'Mineralwasser', 'Gerolsteiner', '{"unit": null, "count": 1, "value": null}', 'wasser', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Naturell}', NULL, '2026-10-12 14:45:09.975665+02');
INSERT INTO public.products VALUES ('p-0023', 'Frischkäse', 'Frischkäse', 'Philadelphia', '{"unit": null, "count": 1, "value": null}', 'frischkaese', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Original}', NULL, '2026-10-12 14:46:54.221882+02');
INSERT INTO public.products VALUES ('p-0001', 'Frische Milch', 'Frische Milch', 'Weihenstephan', '{"unit": null, "count": 1, "value": null}', 'milch', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{"3,5%"}', NULL, '2026-10-12 14:49:14.40275+02');
INSERT INTO public.products VALUES ('p-0002', 'Butter', 'Butter', 'Kerrygold', '{"unit": null, "count": 1, "value": null}', 'butter', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 14:51:34.86821+02');
INSERT INTO public.products VALUES ('p-0003', 'Haferflocken', 'Haferflocken', 'ja!', '{"unit": null, "count": 1, "value": null}', 'muesli', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', '{"file": "fb2fa6a67a60be4129155b7ae9a1069792723fd344b5c3b319f68c2938e929db", "from": "rewe.de", "page": "https://www.rewe.de/shop/p/ja-kernige-haferflocken-500g/1913987", "source": "https://img.rewe-static.de/1913987/21126263_digital-image.png"}', '2026-10-12 14:51:46.431243+02');
INSERT INTO public.products VALUES ('p-0005', 'Taschentücher', 'Taschentücher', 'Tempo', '{"unit": null, "count": 1, "value": null}', 'taschentuecher', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 14:53:14.371106+02');
INSERT INTO public.products VALUES ('p-0007', 'Salatgurke', 'Salatgurke', NULL, '{"unit": null, "count": 1, "value": null}', 'gurken', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 14:53:14.375562+02');
INSERT INTO public.products VALUES ('p-0010', 'H-Milch', 'H-Milch', 'Milsani', '{"unit": null, "count": 1, "value": null}', 'milch', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{"1,5%"}', '{"file": "363a516b810f342c0931ac7f10041e6745e2d231986a37c42e23483bb3f3df35", "from": "aldi-sued.de", "page": "https://www.aldi-sued.de/produkt/milsani-h-milch-1-5-haltbare-fettarme-milch-1-l-000000000000329344", "source": "https://dm.emea.cms.aldi.cx/is/image/aldiprodeu/product/jpg/scaleWidth/300/77877ca1-3275-419d-a3e6-26cccbd340f7/HMilch%2015%20%25%20haltbare%20fettarme%20Milch%201%20l"}', '2026-10-12 14:54:13.920214+02');
INSERT INTO public.products VALUES ('p-0011', 'Rispentomaten', 'Rispentomaten', NULL, '{"unit": null, "count": 1, "value": null}', 'tomaten', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 14:54:13.925471+02');
INSERT INTO public.products VALUES ('p-0012', 'Hähnchenbrustfilet', 'Hähnchenbrustfilet', NULL, '{"unit": null, "count": 1, "value": null}', 'gefluegel', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 14:54:13.928841+02');
INSERT INTO public.products VALUES ('p-0014', 'Haferflocken Bio', 'Haferflocken Bio', NULL, '{"unit": null, "count": 1, "value": null}', 'muesli', true, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 14:54:13.937787+02');
INSERT INTO public.products VALUES ('p-0015', 'Edel-Vollmilchschokolade', 'Edel-Vollmilchschokolade', 'Moser Roth', '{"unit": null, "count": 1, "value": null}', 'schokolade', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 14:55:09.533739+02');
INSERT INTO public.products VALUES ('p-0017', 'Joghurt', 'Joghurt', 'Milsani', '{"unit": null, "count": 1, "value": null}', 'joghurt', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Natur}', '{"file": "5d78f6fa13d591ee9ad8a2ad354c4df7f0a5c6f8966e6491fa31cd2df96e7713", "from": "supermarktcheck.de", "page": "https://www.supermarktcheck.de/product/90406-milsani-joghurt-", "source": "https://media.supermarktcheck.de/product/picture/large_792c6ed06b251d1f37a879dfa2694bb8.jpg"}', '2026-10-12 14:56:13.135456+02');
INSERT INTO public.products VALUES ('p-0018', 'Spaghetti', 'Spaghetti', 'K-Classic', '{"unit": null, "count": 1, "value": null}', 'nudeln', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 14:56:50.516846+02');
INSERT INTO public.products VALUES ('p-0019', 'Alpenmilchschokolade', 'Alpenmilchschokolade', 'Ritter Sport', '{"unit": null, "count": 1, "value": null}', 'schokolade', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 14:57:10.409489+02');
INSERT INTO public.products VALUES ('p-0020', 'Spülmittel', 'Spülmittel', 'Frosch', '{"unit": null, "count": 1, "value": null}', 'spuelmittel', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{Zitrone}', NULL, '2026-10-12 14:57:22.475119+02');
INSERT INTO public.products VALUES ('p-0021', 'Spaghetti', 'Spaghetti', 'Barilla', '{"unit": null, "count": 1, "value": null}', 'nudeln', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{"No. 5"}', NULL, '2026-10-12 14:58:12.732317+02');
INSERT INTO public.products VALUES ('p-0024', 'Toilettenpapier', 'Toilettenpapier', 'Kokett', '{"unit": null, "count": 1, "value": null}', 'toilettenpapier', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', NULL, '2026-10-12 15:00:32.926779+02');
INSERT INTO public.products VALUES ('p-0009', 'Passierte Tomaten', 'Passierte Tomaten', 'Mutti', '{"unit": null, "count": 1, "value": null}', 'gemuesekonserven', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', '{"file": "3076b40b2870ee7543dcbcaf6a459eea9d76c2c2b966578515e45d97caabc2ce", "from": "mutti-parma.com", "page": "https://mutti-parma.com/de/produkte/passierte-tomaten/", "source": "https://mutti-parma.com/app/uploads/sites/15/2019/10/63062-63087-passata-700g-passata.png"}', '2026-10-12 14:44:39.649341+02');
INSERT INTO public.products VALUES ('p-0004', 'Cola', 'Cola', 'Coca-Cola', '{"unit": null, "count": 1, "value": null}', 'limonade', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', '{"file": "fbd243227777827a5923c3176160f2ccf43992854d1f0f5f04eed9ad83cccff5", "from": "rewe.de", "page": "https://www.rewe.de/shop/p/coca-cola-original-taste-1-25l/26109", "source": "https://img.rewe-static.de/0026109/29087985_digital-image.png"}', '2026-10-12 14:52:48.035108+02');
INSERT INTO public.products VALUES ('p-0013', 'Gouda', 'Gouda', NULL, '{"unit": null, "count": 1, "value": null}', 'schnittkaese', NULL, '{}', '{"brand unknown"}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{jung,Scheiben}', NULL, '2026-10-12 14:54:13.934948+02');
INSERT INTO public.products VALUES ('p-0016', 'Duschgel', 'Duschgel', 'Lacura', '{"unit": null, "count": 1, "value": null}', 'duschgel', NULL, '{}', '{}', '{"source": "identify v9", "attributes": "identify", "decided_by": "identify"}', 'null', 'null', 'null', '{}', '{"file": "7d9c3143c3c7deea1051340fd6b00c4639a52d7c0544cb9b3fa857680754d0a2", "from": "aldi-sued.de", "page": "https://www.aldi-sued.de/produkt/lacura-duschgel-400-ml-zitrone-000000000530596001", "source": "https://dm.emea.cms.aldi.cx/is/image/aldiprodeu/product/jpg/scaleWidth/300/8855906f-3790-432c-a6d0-1a884ee0db41/Duschgel%20400%20ml%20Zitrone"}', '2026-10-12 14:55:55.655718+02');


--
-- Data for Name: questions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: receipt_lines; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.receipt_lines VALUES (1, 1, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.49, 0.00, 1.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (2, 1, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.49, 0.00, 2.49, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (3, 1, 2, 'product', 'Ja! Haferflocken 500g', 1, NULL, 0.89, 0.00, 0.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (4, 1, 3, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.69, 0.00, 1.69, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (5, 1, 4, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (6, 1, 5, 'product', 'Tempo Taschent. 10x10', 1, NULL, 2.29, 0.00, 2.29, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (7, 1, 6, 'product', 'Bananen lose', 1, NULL, 1.15, 0.00, 1.15, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (8, 1, 7, 'product', 'Salatgurke St.', 1, NULL, 0.69, 0.00, 0.69, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (9, 1, 8, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (10, 1, 9, 'product', 'Mutti Passata 500g', 1, NULL, 1.29, 0.00, 1.29, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (11, 2, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (12, 2, 1, 'product', 'Rispentomaten 500g', 1, NULL, 1.49, 0.00, 1.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (13, 2, 2, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (14, 2, 3, 'product', 'Hähnchenbrustfilet 400g', 1, NULL, 4.49, 0.00, 4.49, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (15, 2, 4, 'product', 'Gouda jung Scheiben 400g', 1, NULL, 2.79, 0.00, 2.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (16, 2, 5, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (17, 2, 6, 'product', 'Moser Roth Edel-Vollmilch', 1, NULL, 1.39, 0.00, 1.39, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (18, 2, 7, 'product', 'Lacura Duschgel 300ml', 2, NULL, 1.78, -0.36, 1.42, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (19, 2, 8, 'product', 'Kokett Toilettenpapier 8x', 1, NULL, 2.99, 0.00, 2.99, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (20, 2, 9, 'product', 'Milsani Joghurt Natur 500g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (21, 3, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.51, 0.00, 1.51, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (22, 3, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.59, 0.00, 2.59, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (23, 3, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (24, 3, 3, 'product', 'Dr.Oetker Ristorante Salame', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (25, 3, 4, 'product', 'Philadelphia Original 175g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (26, 3, 5, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (27, 3, 6, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (28, 3, 7, 'product', 'Coca-Cola 1,5L', 2, NULL, 3.38, 0.00, 3.38, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (29, 3, 8, 'deposit', 'Pfand', 2, NULL, 0.50, 0.00, 0.50, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (30, 4, 0, 'product', 'Milbona Frische Vollmilch 1L', 1, NULL, 1.11, 0.00, 1.11, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (31, 4, 1, 'product', 'Barissimo Crema Bohnen 1kg', 1, NULL, 13.39, 0.00, 13.39, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (32, 4, 2, 'product', 'Cien Zahncreme 125ml', 1, NULL, 0.65, 0.00, 0.65, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (33, 4, 3, 'product', 'Pilos Schmand 200g', 2, NULL, 1.58, 0.00, 1.58, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (34, 4, 4, 'product', 'Freeway Cola 1,5L', 1, NULL, 0.65, 0.00, 0.65, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (35, 4, 5, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (36, 4, 6, 'product', 'Salatgurke', 1, NULL, 0.64, 0.00, 0.64, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (37, 5, 0, 'product', 'Rispentomaten 500g', 1, NULL, 1.55, 0.00, 1.55, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (38, 5, 1, 'product', 'Bananen', 2, NULL, 2.38, 0.00, 2.38, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (39, 5, 2, 'product', 'Milsani Joghurt Natur 500g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (40, 5, 3, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (41, 5, 4, 'product', 'Hähnchenbrustfilet 400g', 2, NULL, 9.18, 0.00, 9.18, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (42, 5, 5, 'product', 'Lacura Duschgel 300ml', 1, NULL, 0.89, 0.00, 0.89, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (43, 6, 0, 'product', 'K-Classic Spaghetti 500g', 1, NULL, 0.79, 0.00, 0.79, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (44, 6, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.47, 0.00, 2.47, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (45, 6, 2, 'product', 'Ritter Sport Alpenmilch 100g', 2, NULL, 3.08, 0.00, 3.08, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (46, 6, 3, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.59, 0.00, 1.59, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (47, 6, 4, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (48, 6, 5, 'product', 'Frosch Spülmittel Zitrone', 1, NULL, 1.19, -0.24, 0.95, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (49, 7, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.53, 0.00, 1.53, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (50, 7, 1, 'product', 'Kerrygold Butter 250g', 2, NULL, 5.38, 0.00, 5.38, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (51, 7, 2, 'product', 'Barilla Spaghetti No.5 500g', 2, NULL, 3.58, 0.00, 3.58, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (52, 7, 3, 'product', 'Coca-Cola 1,5L', 1, NULL, 1.69, -0.34, 1.35, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (53, 7, 4, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (54, 7, 5, 'product', 'Gerolsteiner Naturell 1,5L', 1, NULL, 0.79, 0.00, 0.79, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (55, 7, 6, 'deposit', 'Pfand', 1, NULL, 0.25, 0.00, 0.25, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (56, 7, 7, 'product', 'Philadelphia Original 175g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (57, 8, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.55, 0.00, 1.55, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (58, 8, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.79, 0.00, 2.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (59, 8, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (60, 8, 3, 'product', 'Tempo Taschent. 10x10', 1, NULL, 2.29, 0.00, 2.29, '1', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (61, 8, 4, 'product', 'Philadelphia Original 175g', 1, NULL, 1.99, 0.00, 1.99, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (62, 8, 5, 'product', 'Rispentomaten lose', 2, NULL, 3.68, 0.00, 3.68, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (63, 9, 0, 'product', 'Milsani H-Milch 1,5% 1L', 1, NULL, 1.07, 0.00, 1.07, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (64, 9, 1, 'product', 'Rispentomaten 500g', 2, NULL, 3.46, 0.00, 3.46, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (65, 9, 2, 'product', 'Bananen', 1, NULL, 1.19, 0.00, 1.19, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (66, 9, 3, 'product', 'Hähnchenbrustfilet 400g', 1, NULL, 4.89, 0.00, 4.89, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (67, 9, 4, 'product', 'Kokett Toilettenpapier 8x', 1, NULL, 2.99, 0.00, 2.99, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (68, 9, 5, 'product', 'Gouda jung Scheiben 400g', 1, NULL, 2.99, 0.00, 2.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (69, 9, 6, 'product', 'Bio Haferflocken 500g', 1, NULL, 0.99, 0.00, 0.99, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (70, 9, 7, 'product', 'Milsani Joghurt Natur 500g', 1, NULL, 0.79, 0.00, 0.79, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (71, 9, 8, 'product', 'Moser Roth Edel-Vollmilch', 2, NULL, 2.78, 0.00, 2.78, 'A', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (72, 9, 9, 'product', 'Lacura Duschgel 300ml', 2, NULL, 1.78, 0.00, 1.78, 'B', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (73, 10, 0, 'product', 'Weihenst. Frische Milch 3,5% 1L', 1, NULL, 1.57, 0.00, 1.57, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (74, 10, 1, 'product', 'Kerrygold Butter 250g', 1, NULL, 2.89, 0.00, 2.89, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (75, 10, 2, 'product', 'Barilla Spaghetti No.5 500g', 1, NULL, 1.79, 0.00, 1.79, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (76, 10, 3, 'product', 'Bananen lose', 1, NULL, 1.15, 0.00, 1.15, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (77, 10, 4, 'product', 'Philadelphia Original 175g', 2, NULL, 3.98, 0.00, 3.98, '2', NULL, NULL, NULL, NULL);
INSERT INTO public.receipt_lines VALUES (78, 10, 5, 'product', 'Tempo Taschent. 10x10', 1, NULL, 2.29, 0.00, 2.29, '1', NULL, NULL, NULL, NULL);


--
-- Data for Name: receipts; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.receipts VALUES (1, '6501ba0bff41f081f734af3737680a6ac646d14daf33987fc8b27b5209f662cb', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-06-21', '16:35', 'EUR', 15.02, NULL, '{"7%": 10.79, "19%": 4.23}', '2026-10-12 14:12:37.474929+02', '6501ba0bff41f081f734af3737680a6ac646d14daf33987fc8b27b5209f662cb', NULL);
INSERT INTO public.receipts VALUES (2, 'f6d822434fc129ea2a692964fb69360a22aa15540d9be35a8919aaffebf49461', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-06-27', '17:42', 'EUR', 18.53, 0.36, '{"7%": 14.12, "19%": 4.41}', '2026-10-12 14:20:48.530591+02', 'f6d822434fc129ea2a692964fb69360a22aa15540d9be35a8919aaffebf49461', NULL);
INSERT INTO public.receipts VALUES (3, 'e3377b57e73c8e41c3ffd43ec5c3a8fec37aebcda0c63b9ecc5ad7df814f0028', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-07-04', '09:45', 'EUR', 15.59, NULL, '{"7%": 10.67, "19%": 4.92}', '2026-10-12 14:27:44.293169+02', 'e3377b57e73c8e41c3ffd43ec5c3a8fec37aebcda0c63b9ecc5ad7df814f0028', NULL);
INSERT INTO public.receipts VALUES (4, 'a7727d8c4459ceabc7e3bf88d80341f54bb61949453e454471359a4fac18e63f', 'made-up', 'Lidl', 'Probeplatz 3, 66117 Saarbrücken', '2026-07-04', '15:31', 'EUR', 18.27, NULL, '{"7%": 16.72, "19%": 1.55}', '2026-10-12 14:28:31.268478+02', 'a7727d8c4459ceabc7e3bf88d80341f54bb61949453e454471359a4fac18e63f', NULL);
INSERT INTO public.receipts VALUES (5, 'eff65a36244342973ff76be0f3d146394f10a9d776c95d7bafeaa7e335d491f6', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-07-15', '11:58', 'EUR', 15.78, NULL, '{"7%": 14.89, "19%": 0.89}', '2026-10-12 14:31:32.552467+02', 'eff65a36244342973ff76be0f3d146394f10a9d776c95d7bafeaa7e335d491f6', NULL);
INSERT INTO public.receipts VALUES (6, '93d59e809840916984cd9374e555e1b60b2cb5e5be6ed8a9b5a504bbe6143668', 'made-up', 'Kaufland', 'Testallee 9, 66119 Saarbrücken', '2026-07-18', '12:48', 'EUR', 9.13, 0.24, '{"7%": 6.34, "19%": 2.79}', '2026-10-12 14:32:24.979435+02', '93d59e809840916984cd9374e555e1b60b2cb5e5be6ed8a9b5a504bbe6143668', NULL);
INSERT INTO public.receipts VALUES (7, '8f8a6007d4a0cdb156b0b395977fddf1368f739bcba10e040535a45537d61845', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-08-28', '11:53', 'EUR', 15.12, 0.34, '{"7%": 12.48, "19%": 2.64}', '2026-10-12 14:38:06.136885+02', '8f8a6007d4a0cdb156b0b395977fddf1368f739bcba10e040535a45537d61845', NULL);
INSERT INTO public.receipts VALUES (8, '94aab3e2bc34e5b4f753d8f4076e9669bfc251b88495c1dcda556cce66848eee', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-09-14', '10:07', 'EUR', 14.09, NULL, '{"7%": 11.8, "19%": 2.29}', '2026-10-12 14:40:16.72833+02', '94aab3e2bc34e5b4f753d8f4076e9669bfc251b88495c1dcda556cce66848eee', NULL);
INSERT INTO public.receipts VALUES (9, '27240d4b650bf58b65f8f53fa5e669d2158a60165706b410abc794790493a892', 'made-up', 'ALDI SÜD', 'Beispielweg 5, 66113 Saarbrücken', '2026-10-10', '13:33', 'EUR', 22.93, NULL, '{"7%": 18.16, "19%": 4.77}', '2026-10-12 14:40:16.775622+02', '27240d4b650bf58b65f8f53fa5e669d2158a60165706b410abc794790493a892', NULL);
INSERT INTO public.receipts VALUES (10, 'e60b676b22e46af55d670adc220ba38167ca2feb24873f729b27acb0b1f60011', 'made-up', 'GLOBUS', 'Musterstraße 1, 66111 Saarbrücken', '2026-10-10', '19:17', 'EUR', 13.67, NULL, '{"7%": 11.38, "19%": 2.29}', '2026-10-12 14:41:03.812+02', 'e60b676b22e46af55d670adc220ba38167ca2feb24873f729b27acb0b1f60011', NULL);


--
-- Data for Name: resolutions; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.resolutions VALUES (1, 'GLOBUS', 'Weihenst. Frische Milch 3,5% 1L', 'product', 'p-0001', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (2, 'GLOBUS', 'Kerrygold Butter 250g', 'product', 'p-0002', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (3, 'GLOBUS', 'Ja! Haferflocken 500g', 'product', 'p-0003', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (4, 'GLOBUS', 'Coca-Cola 1,5L', 'product', 'p-0004', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (5, 'GLOBUS', 'Tempo Taschent. 10x10', 'product', 'p-0005', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (6, 'GLOBUS', 'Bananen lose', 'product', 'p-0006', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (7, 'GLOBUS', 'Salatgurke St.', 'product', 'p-0007', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (8, 'GLOBUS', 'Dr.Oetker Ristorante Salame', 'product', 'p-0008', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (9, 'GLOBUS', 'Mutti Passata 500g', 'product', 'p-0009', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (10, 'ALDI SÜD', 'Milsani H-Milch 1,5% 1L', 'product', 'p-0010', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (11, 'ALDI SÜD', 'Rispentomaten 500g', 'product', 'p-0011', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (12, 'ALDI SÜD', 'Hähnchenbrustfilet 400g', 'product', 'p-0012', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (13, 'ALDI SÜD', 'Gouda jung Scheiben 400g', 'product', 'p-0013', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (14, 'ALDI SÜD', 'Bio Haferflocken 500g', 'product', 'p-0014', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (15, 'ALDI SÜD', 'Moser Roth Edel-Vollmilch', 'product', 'p-0015', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (16, 'ALDI SÜD', 'Lacura Duschgel 300ml', 'product', 'p-0016', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (17, 'ALDI SÜD', 'Milsani Joghurt Natur 500g', 'product', 'p-0017', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (18, 'Kaufland', 'K-Classic Spaghetti 500g', 'product', 'p-0018', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (19, 'Kaufland', 'Kerrygold Butter 250g', 'product', 'p-0002', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (20, 'Kaufland', 'Ritter Sport Alpenmilch 100g', 'product', 'p-0019', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (21, 'Kaufland', 'Coca-Cola 1,5L', 'product', 'p-0004', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (22, 'Kaufland', 'Frosch Spülmittel Zitrone', 'product', 'p-0020', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (23, 'GLOBUS', 'Barilla Spaghetti No.5 500g', 'product', 'p-0021', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (24, 'GLOBUS', 'Gerolsteiner Naturell 1,5L', 'product', 'p-0022', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (25, 'GLOBUS', 'Philadelphia Original 175g', 'product', 'p-0023', '{}', NULL, 'identify', '2026-10-12', 'identify v9');
INSERT INTO public.resolutions VALUES (26, 'ALDI SÜD', 'Kokett Toilettenpapier 8x', 'product', 'p-0024', '{}', NULL, 'identify', '2026-10-12', 'identify v9');


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

SELECT pg_catalog.setval('public.checks_id_seq', 10, true);


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

SELECT pg_catalog.setval('public.model_calls_id_seq', 167, true);


--
-- Name: questions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.questions_id_seq', 1, false);


--
-- Name: receipt_lines_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.receipt_lines_id_seq', 78, true);


--
-- Name: receipts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.receipts_id_seq', 10, true);


--
-- Name: resolutions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.resolutions_id_seq', 26, true);


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

\unrestrict qFx5eKZanRqMG9ij01yKV9Thm4RlhkhxJpzfU28Hajg25adr5PImAEw4IDkYRb8

