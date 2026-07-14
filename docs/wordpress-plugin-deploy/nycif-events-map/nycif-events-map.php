<?php
/**
 * Plugin Name: NYCIF Events Map
 * Plugin URI: https://github.com/setoxxx/nycif-live-feeds
 * Description: Embeds the NYC In Focus live event map (GitHub Pages) with staged feed data from nycif-live-feeds. Emergency map restore 1.2.1.
 * Version: 1.2.1
 * Author: NYC In Focus
 * License: GPL-2.0-or-later
 * Text Domain: nycif-events-map
 */

if (!defined('ABSPATH')) {
    exit;
}

define('NYCIF_EVENTS_MAP_VERSION', '1.2.1');

/** GitHub Pages map — restored staged-live runtime */
define('NYCIF_MAP_EMBED_URL', 'https://setoxxx.github.io/nycif-field-desk/');

/** Raw feed URLs for diagnostics only — WordPress must not fetch/parse the JSON feed */
define('NYCIF_STAGED_FEED_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json');
define('NYCIF_ALL_FEED_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_all_radar_map_events.json');
define('NYCIF_DASHBOARD_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-live-pipeline-dashboard.json');

/**
 * Register shortcode [nycif_events_map]
 *
 * Attributes:
 *   height — iframe height CSS (default 85vh)
 *   cache  — cache-bust query string (default map-restore-v01)
 */
function nycif_events_map_shortcode($atts) {
    $atts = shortcode_atts(
        array(
            'height' => '85vh',
            'cache'  => 'map-restore-v01',
        ),
        $atts,
        'nycif_events_map'
    );

    $src = add_query_arg(
        array(
            'v'            => sanitize_text_field($atts['cache']),
            'resetFilters' => '1',
        ),
        NYCIF_MAP_EMBED_URL
    );

    $height = esc_attr($atts['height']);
    $src_esc = esc_url($src);

    return sprintf(
        '<div class="nycif-events-map-wrap" style="width:100%%;max-width:100%%;margin:0 auto;">'
        . '<iframe class="nycif-events-map-iframe" title="NYC In Focus Event Map" '
        . 'src="%s" style="width:100%%;height:%s;border:0;border-radius:12px;" '
        . 'loading="eager" allowfullscreen '
        . 'referrerpolicy="no-referrer-when-downgrade" allow="geolocation; fullscreen"></iframe>'
        . '<p class="nycif-events-map-caption" style="font-size:12px;color:#666;margin-top:8px;">'
        . 'Live NYC permit events via NYCIF staged feed. Event details may change; confirm before traveling.'
        . '</p></div>',
        $src_esc,
        $height
    );
}
add_shortcode('nycif_events_map', 'nycif_events_map_shortcode');

/**
 * Admin notice with feed freshness link (Settings → NYCIF Map)
 */
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
    ?>
    <div class="wrap">
        <h1>NYCIF Events Map</h1>
        <p>Plugin version <?php echo esc_html(NYCIF_EVENTS_MAP_VERSION); ?></p>
        <table class="form-table">
            <tr><th>Embed URL</th><td><code><?php echo esc_html(NYCIF_MAP_EMBED_URL); ?></code></td></tr>
            <tr><th>Default iframe query</th><td><code>?v=map-restore-v01&amp;resetFilters=1</code></td></tr>
            <tr><th>Staged feed (backend only)</th><td><code><?php echo esc_html(NYCIF_STAGED_FEED_URL); ?></code></td></tr>
            <tr><th>Full feed (backend only)</th><td><code><?php echo esc_html(NYCIF_ALL_FEED_URL); ?></code></td></tr>
            <tr><th>Pipeline dashboard</th><td><a href="<?php echo esc_url(NYCIF_DASHBOARD_URL); ?>" target="_blank" rel="noopener">Open JSON</a></td></tr>
        </table>
        <p>Shortcode: <code>[nycif_events_map]</code> or <code>[nycif_events_map height="90vh" cache="custom-bust"]</code></p>
        <p><strong>Deploy note (1.2.1):</strong> Merge and deploy the Field Desk emergency map restore to GitHub Pages before uploading this plugin ZIP. This plugin is an iframe wrapper only and does not fetch the 32k-event JSON.</p>
    </div>
    <?php
}

/**
 * Block theme / FSE: optional block registration stub for future
 */
function nycif_events_map_register_block() {
    if (!function_exists('register_block_type')) {
        return;
    }
    register_block_type('nycif/events-map', array(
        'render_callback' => function () {
            return nycif_events_map_shortcode(array());
        },
    ));
}
add_action('init', 'nycif_events_map_register_block');
