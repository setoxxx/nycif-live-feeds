<?php
/**
 * Plugin Name: NYCIF Events Map
 * Plugin URI: https://github.com/setoxxx/nycif-live-feeds
 * Description: Embeds the NYC In Focus public event map (schema-v1-discovery, feeds=main) for in-article WordPress pages. Production /map/ uses the fullscreen shell in the freeze doc — not this shortcode.
 * Version: 1.5.0-rc1
 * Author: NYC In Focus
 * License: GPL-2.0-or-later
 * Text Domain: nycif-events-map
 */

if (!defined('ABSPATH')) {
    exit;
}

define('NYCIF_EVENTS_MAP_VERSION', '1.5.0-rc1');
define('NYCIF_MAP_EMBED_URL', 'https://setoxxx.github.io/nycif-field-desk/');
define('NYCIF_PUBLIC_MAP_URL', 'https://nycinfocus.com/map/');
define('NYCIF_APPROVED_FEED_REF', 'main');
define('NYCIF_RUNTIME_CACHE_BUST', 'public-map-v10');
define('NYCIF_FIELD_DESK_REPO_URL', 'https://github.com/setoxxx/nycif-field-desk');
define('NYCIF_LIVE_FEEDS_REPO_URL', 'https://github.com/setoxxx/nycif-live-feeds');
define('NYCIF_FREEZE_DOC_PATH', 'docs/wordpress-plugin-deploy/nycinfocus-map-page-v1-freeze.md');
define('NYCIF_STAGED_FEED_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json');
define('NYCIF_PIPELINE_DASHBOARD_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-live-pipeline-dashboard.json');
define('NYCIF_ROLLBACK_PACKAGE', 'nycif-events-map-1.4.0-rc1.zip');
define('NYCIF_ROLLBACK_SHA256', 'ea5b0ac0632fe09f99758b34cab67fa45bf753be4ca724b9bdeb5fa0d79101e9');

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
 * Normalize feeds= for public embeds. Retired commit-SHA pins map to main.
 *
 * @param string $feeds Raw feeds attribute.
 * @return string
 */
function nycif_events_map_normalize_feeds($feeds) {
    $feeds = sanitize_text_field($feeds);

    if ($feeds === '') {
        return NYCIF_APPROVED_FEED_REF;
    }

    // Retired: 1.4.0-rc1 pinned feeds= to a git commit SHA. Public embeds use main only.
    if (preg_match('/^[a-f0-9]{40}$/i', $feeds)) {
        return NYCIF_APPROVED_FEED_REF;
    }

    return $feeds;
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
            'feed_ref'      => '', // Deprecated alias from 1.4.0-rc1 — ignored when commit SHA.
            'reset_filters' => '1',
            'clusters'      => '0',
        ),
        $atts,
        'nycif_events_map'
    );

    $height = sanitize_text_field($atts['height']);
    if (!preg_match('/^\d+(?:\.\d+)?(?:px|vh|vw|rem|em|%)$/', $height)) {
        $height = '85vh';
    }

    $feeds = nycif_events_map_normalize_feeds($atts['feeds']);
    if ($feeds === NYCIF_APPROVED_FEED_REF && $atts['feed_ref'] !== '') {
        $feeds = nycif_events_map_normalize_feeds($atts['feed_ref']);
    }

    $query_args = array(
        'v'     => sanitize_text_field($atts['cache']),
        'feeds' => $feeds,
    );

    if ('1' === (string) $atts['reset_filters']) {
        $query_args['resetFilters'] = '1';
    }

    if ('1' === (string) $atts['clusters']) {
        $query_args['clusters'] = '1';
    }

    $src = add_query_arg($query_args, NYCIF_MAP_EMBED_URL);

    return sprintf(
        '<div class="nycif-events-map-wrap" style="width:100%%;max-width:100%%;margin:0 auto;">'
        . '<iframe class="nycif-events-map-iframe" title="NYC In Focus Event Map" '
        . 'src="%s" style="width:100%%;height:%s;border:0;border-radius:12px;" '
        . 'loading="eager" referrerpolicy="no-referrer-when-downgrade" '
        . 'allow="geolocation; fullscreen" allowfullscreen></iframe>'
        . '<p class="nycif-events-map-caption" style="font-size:12px;color:#666;margin-top:8px;">'
        . 'Live NYC public events from the approved discovery feed (feeds=main). Event details may change; confirm before traveling.'
        . '</p></div>',
        esc_url($src),
        esc_attr($height)
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
                See repo freeze doc: <code><?php echo esc_html(NYCIF_FREEZE_DOC_PATH); ?></code>
            </p>
            <p>Mobile vs desktop layout is automatic inside the iframe (≤720px mobile, ≥721px desktop).</p>
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
                <th>Approved feed</th>
                <td><code>feeds=<?php echo esc_html(NYCIF_APPROVED_FEED_REF); ?></code> (not a git commit SHA)</td>
            </tr>
            <tr>
                <th>Field Desk repository</th>
                <td><a href="<?php echo esc_url(NYCIF_FIELD_DESK_REPO_URL); ?>" target="_blank" rel="noopener">Open repository</a></td>
            </tr>
            <tr>
                <th>Live-feeds repository</th>
                <td><a href="<?php echo esc_url(NYCIF_LIVE_FEEDS_REPO_URL); ?>" target="_blank" rel="noopener">Open repository</a></td>
            </tr>
            <tr>
                <th>Pipeline dashboard (JSON)</th>
                <td><a href="<?php echo esc_url(NYCIF_PIPELINE_DASHBOARD_URL); ?>" target="_blank" rel="noopener">Open status JSON</a></td>
            </tr>
            <tr>
                <th>Staged feed (pipeline only)</th>
                <td><code><?php echo esc_html(NYCIF_STAGED_FEED_URL); ?></code><p class="description">Not loaded by this plugin on public embeds.</p></td>
            </tr>
            <tr>
                <th>Rollback ZIP</th>
                <td><code><?php echo esc_html(NYCIF_ROLLBACK_PACKAGE); ?></code></td>
            </tr>
            <tr>
                <th>Rollback SHA-256</th>
                <td><code><?php echo esc_html(NYCIF_ROLLBACK_SHA256); ?></code></td>
            </tr>
        </table>

        <h2>Shortcode (in-article embeds)</h2>
        <p><code>[nycif_events_map]</code></p>
        <p>Optional: <code>[nycif_events_map height="90vh" cache="<?php echo esc_html(NYCIF_RUNTIME_CACHE_BUST); ?>" feeds="main" clusters="1"]</code></p>
        <p class="description">Retired: <code>feed_ref=&lt;commit-sha&gt;</code>, <code>v=discovery-taxonomy-v03</code>, <code>?feed=staged</code>.</p>

        <h2>Release notes (1.5.0-rc1)</h2>
        <ul style="list-style:disc;margin-left:20px;">
            <li>Aligns with RC public map <code><?php echo esc_html(NYCIF_RUNTIME_CACHE_BUST); ?></code> and <code>feeds=main</code>.</li>
            <li>Replaces 1.4.0-rc1 commit-pinned feed with approved discovery contract.</li>
            <li>Device-aware layout runs inside the iframe; WordPress shell unchanged for /map/.</li>
            <li>GPS review / supplemental staging artifacts are never exposed via this plugin.</li>
        </ul>
    </div>
    <?php
}

function nycif_events_map_register_block() {
    if (!function_exists('register_block_type')) {
        return;
    }

    register_block_type(
        'nycif/events-map',
        array(
            'render_callback' => function () {
                return nycif_events_map_shortcode(array());
            },
        )
    );
}
add_action('init', 'nycif_events_map_register_block');
