<?php
/**
 * Plugin Name: NYCIF Events Map
 * Plugin URI: https://github.com/setoxxx/nycif-live-feeds
 * Description: Embeds the NYC In Focus public event map (schema-v1-discovery, feeds=main) for in-article WordPress pages. Production /map/ uses the fullscreen shell in the freeze doc — not this shortcode.
 * Version: 1.5.0-rc2
 * Author: NYC In Focus
 * License: GPL-2.0-or-later
 * Text Domain: nycif-events-map
 */

if (!defined('ABSPATH')) {
    exit;
}

define('NYCIF_EVENTS_MAP_VERSION', '1.5.0-rc2');
define('NYCIF_MAP_EMBED_URL', 'https://setoxxx.github.io/nycif-field-desk/');
define('NYCIF_PUBLIC_MAP_URL', 'https://nycinfocus.com/map/');
define('NYCIF_APPROVED_FEED_REF', 'main');
define('NYCIF_RUNTIME_CACHE_BUST', 'public-map-v10');
define('NYCIF_FIELD_DESK_REPO_URL', 'https://github.com/setoxxx/nycif-field-desk');
define('NYCIF_LIVE_FEEDS_REPO_URL', 'https://github.com/setoxxx/nycif-live-feeds');
define('NYCIF_FREEZE_DOC_PATH', 'docs/wordpress-plugin-deploy/nycinfocus-map-page-v1-freeze.md');
define('NYCIF_DEPLOY_RUNBOOK_PATH', 'docs/wordpress-plugin-deploy/CHATGPT-EXECUTION-PROMPT.md');
define('NYCIF_STAGED_FEED_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json');
define('NYCIF_PIPELINE_DASHBOARD_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-live-pipeline-dashboard.json');
define('NYCIF_DISCOVERY_MANIFEST_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/schema-v1-discovery/approved/manifest.json');
define('NYCIF_ROLLBACK_PACKAGE', 'nycif-events-map-1.4.0-rc1.zip');
define('NYCIF_ROLLBACK_SHA256', 'ea5b0ac0632fe09f99758b34cab67fa45bf753be4ca724b9bdeb5fa0d79101e9');

/**
 * Approved public feed refs for this plugin (allowlist).
 *
 * @return string[]
 */
function nycif_events_map_allowed_feed_refs() {
    return array(NYCIF_APPROVED_FEED_REF);
}

/**
 * Approved runtime cache-bust tokens for this plugin (allowlist).
 *
 * @return string[]
 */
function nycif_events_map_allowed_runtime_tokens() {
    return array(NYCIF_RUNTIME_CACHE_BUST);
}

/**
 * Build the canonical Field Desk iframe URL for approved public discovery.
 *
 * @param array $overrides Optional query overrides (v, feeds, resetFilters, clusters).
 * @return string
 */
function nycif_events_map_runtime_url($overrides = array()) {
    $query_args = array_merge(
        array(
            'v'            => NYCIF_RUNTIME_CACHE_BUST,
            'feeds'        => NYCIF_APPROVED_FEED_REF,
            'resetFilters' => '1',
        ),
        $overrides
    );

    return add_query_arg($query_args, NYCIF_MAP_EMBED_URL);
}

/**
 * Normalize feeds= to the approved allowlist (main only).
 *
 * @param string $feeds Raw feeds attribute.
 * @param bool   $was_rewritten Set true when a non-allowlisted value was rewritten.
 * @return string
 */
function nycif_events_map_normalize_feeds($feeds, &$was_rewritten = false) {
    $was_rewritten = false;
    $feeds = sanitize_text_field($feeds);

    if ($feeds === '' || $feeds === NYCIF_APPROVED_FEED_REF) {
        return NYCIF_APPROVED_FEED_REF;
    }

    $was_rewritten = true;
    return NYCIF_APPROVED_FEED_REF;
}

/**
 * Normalize runtime cache token to the approved allowlist.
 *
 * @param string $cache Raw cache attribute.
 * @param bool   $was_rewritten Set true when a non-allowlisted value was rewritten.
 * @return string
 */
function nycif_events_map_normalize_cache($cache, &$was_rewritten = false) {
    $was_rewritten = false;
    $cache = sanitize_text_field($cache);

    if ($cache === '' || $cache === NYCIF_RUNTIME_CACHE_BUST) {
        return NYCIF_RUNTIME_CACHE_BUST;
    }

    $was_rewritten = true;
    return NYCIF_RUNTIME_CACHE_BUST;
}

/**
 * Shortcode: in-article embed only. Do not use on production /map/ (see freeze doc).
 *
 * @param array|string $atts Shortcode attributes.
 * @return string
 */
function nycif_events_map_shortcode($atts) {
    $atts = shortcode_atts(
        array(
            'height'        => '85vh',
            'cache'         => NYCIF_RUNTIME_CACHE_BUST,
            'feeds'         => NYCIF_APPROVED_FEED_REF,
            'feed_ref'      => '',
            'reset_filters' => '1',
            'clusters'      => '0',
            'loading'       => 'lazy',
        ),
        $atts,
        'nycif_events_map'
    );

    $height = sanitize_text_field($atts['height']);
    if (!preg_match('/^\d+(?:\.\d+)?(?:px|vh|vw|rem|em|%)$/', $height)) {
        $height = '85vh';
    }

    $loading = sanitize_key($atts['loading']);
    if (!in_array($loading, array('lazy', 'eager'), true)) {
        $loading = 'lazy';
    }

    $feeds_rewritten = false;
    $cache_rewritten = false;
    $feeds = nycif_events_map_normalize_feeds($atts['feeds'], $feeds_rewritten);
    if ($atts['feed_ref'] !== '' && $atts['feed_ref'] !== NYCIF_APPROVED_FEED_REF) {
        nycif_events_map_normalize_feeds($atts['feed_ref'], $feeds_rewritten);
        $feeds = NYCIF_APPROVED_FEED_REF;
    }
    $cache = nycif_events_map_normalize_cache($atts['cache'], $cache_rewritten);

    $query_args = array(
        'v'     => $cache,
        'feeds' => $feeds,
    );

    if ('1' === (string) $atts['reset_filters']) {
        $query_args['resetFilters'] = '1';
    }

    if ('1' === (string) $atts['clusters']) {
        $query_args['clusters'] = '1';
    }

    $src = add_query_arg($query_args, NYCIF_MAP_EMBED_URL);

    $admin_notice = '';
    if (($feeds_rewritten || $cache_rewritten) && function_exists('current_user_can') && current_user_can('manage_options')) {
        $admin_notice = '<p class="nycif-events-map-admin-notice" style="font-size:11px;color:#b45309;margin:0 0 8px;">'
            . 'NYCIF admin: non-approved <code>feeds</code> or <code>cache</code> value was rewritten to '
            . '<code>feeds=main</code> and <code>v=' . esc_html(NYCIF_RUNTIME_CACHE_BUST) . '</code>. Update the shortcode.'
            . '</p>';
    }

    return sprintf(
        '<div class="nycif-events-map-wrap" style="width:100%%;max-width:100%%;margin:0 auto;">'
        . '%s'
        . '<iframe class="nycif-events-map-iframe" title="NYC In Focus Event Map" '
        . 'src="%s" style="width:100%%;height:%s;border:0;border-radius:12px;" '
        . 'loading="%s" referrerpolicy="strict-origin-when-cross-origin" '
        . 'allow="geolocation; fullscreen" allowfullscreen></iframe>'
        . '<p class="nycif-events-map-caption" style="font-size:12px;color:#666;margin-top:8px;">'
        . 'Live NYC public events from the approved discovery feed (feeds=main). Event details may change; confirm before traveling.'
        . '</p></div>',
        $admin_notice,
        esc_url($src),
        esc_attr($height),
        esc_attr($loading)
    );
}
add_shortcode('nycif_events_map', 'nycif_events_map_shortcode');

function nycif_events_map_settings_page() {
    add_options_page(
        'NYCIF Events Map',
        'NYCIF Events Map',
        'manage_options',
        'nycif-events-map',
        'nycif_events_map_settings_render'
    );
}
add_action('admin_menu', 'nycif_events_map_settings_page');

function nycif_events_map_admin_notice_commit_pin() {
    if (!current_user_can('manage_options')) {
        return;
    }
    $screen = function_exists('get_current_screen') ? get_current_screen() : null;
    if (!$screen || $screen->id !== 'settings_page_nycif-events-map') {
        return;
    }
    echo '<div class="notice notice-warning"><p><strong>Public embed allowlist:</strong> '
        . 'only <code>feeds=main</code> and <code>v=' . esc_html(NYCIF_RUNTIME_CACHE_BUST) . '</code> are permitted. '
        . 'Commit SHA pins and staging feeds are rejected. '
        . '<code>v=</code> is a cache-bust label; runtime rollback = redeploy <code>setoxxx/nycif-field-desk</code> via GitHub Actions.</p></div>';
}
add_action('admin_notices', 'nycif_events_map_admin_notice_commit_pin');

function nycif_events_map_settings_render() {
    if (!current_user_can('manage_options')) {
        return;
    }

    $runtime_url = nycif_events_map_runtime_url();
    ?>
    <div class="wrap">
        <h1>NYCIF Events Map</h1>
        <p><strong>Plugin version:</strong> <?php echo esc_html(NYCIF_EVENTS_MAP_VERSION); ?></p>

        <div class="notice notice-warning inline" style="margin:12px 0;padding:12px;">
            <p><strong>Production map page:</strong>
                <a href="<?php echo esc_url(NYCIF_PUBLIC_MAP_URL); ?>" target="_blank" rel="noopener"><?php echo esc_html(NYCIF_PUBLIC_MAP_URL); ?></a>
                uses a <strong>fullscreen Custom HTML shell</strong> (WordPress page 2647), <em>not</em> this shortcode.
            </p>
            <p><code>v=<?php echo esc_html(NYCIF_RUNTIME_CACHE_BUST); ?></code> is a cache-bust query label. Real runtime rollback = redeploy a known-good commit to <code>setoxxx/nycif-field-desk</code> via GitHub Actions.</p>
            <p><code>feeds=main</code> is an intentionally mutable live data channel (always current discovery on <code>main</code>).</p>
        </div>

        <table class="form-table">
            <tr>
                <th>Canonical runtime URL</th>
                <td>
                    <code><?php echo esc_html($runtime_url); ?></code>
                    <p class="description"><a href="<?php echo esc_url($runtime_url); ?>" target="_blank" rel="noopener">Open on GitHub Pages</a></p>
                </td>
            </tr>
            <tr>
                <th>Runtime cache bust (<code>v=</code>)</th>
                <td><code><?php echo esc_html(NYCIF_RUNTIME_CACHE_BUST); ?></code></td>
            </tr>
            <tr>
                <th>Approved feed channel</th>
                <td><code>feeds=<?php echo esc_html(NYCIF_APPROVED_FEED_REF); ?></code> (allowlist — other values rejected)</td>
            </tr>
            <tr>
                <th>Discovery manifest (snapshot probe)</th>
                <td><a href="<?php echo esc_url(NYCIF_DISCOVERY_MANIFEST_URL); ?>" target="_blank" rel="noopener">Open manifest JSON</a></td>
            </tr>
            <tr>
                <th>Field Desk deploy repo</th>
                <td><a href="<?php echo esc_url(NYCIF_FIELD_DESK_REPO_URL); ?>" target="_blank" rel="noopener">setoxxx/nycif-field-desk</a></td>
            </tr>
            <tr>
                <th>Live-feeds repo</th>
                <td><a href="<?php echo esc_url(NYCIF_LIVE_FEEDS_REPO_URL); ?>" target="_blank" rel="noopener">setoxxx/nycif-live-feeds</a></td>
            </tr>
            <tr>
                <th>Deploy workflow (live-feeds)</th>
                <td><code>.github/workflows/field-desk-complete-map-deploy.yml</code> — must PASS before WordPress</td>
            </tr>
            <tr>
                <th>Plugin rollback ZIP</th>
                <td><code><?php echo esc_html(NYCIF_ROLLBACK_PACKAGE); ?></code></td>
            </tr>
        </table>

        <h2>Shortcode (in-article embeds)</h2>
        <p><code>[nycif_events_map]</code> — defaults to <code>loading="lazy"</code></p>
        <p>Optional: <code>[nycif_events_map height="90vh" cache="<?php echo esc_html(NYCIF_RUNTIME_CACHE_BUST); ?>" feeds="main" loading="lazy" clusters="1"]</code></p>

        <h2>Block editor</h2>
        <p>Dynamic block <code>nycif/events-map</code> is registered via <code>block.json</code> (server-rendered; no client editor script). Search the inserter for <strong>NYCIF Events Map</strong>, or use the shortcode above.</p>
    </div>
    <?php
}

function nycif_events_map_register_block() {
    if (!function_exists('register_block_type')) {
        return;
    }

    register_block_type(
        __DIR__ . '/block.json',
        array(
            'render_callback' => function ($attributes) {
                return nycif_events_map_shortcode($attributes);
            },
        )
    );
}
add_action('init', 'nycif_events_map_register_block');
