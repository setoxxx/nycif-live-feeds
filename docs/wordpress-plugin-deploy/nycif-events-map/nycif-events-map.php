<?php
/**
 * Plugin Name: NYCIF Events Map
 * Plugin URI: https://github.com/setoxxx/nycif-live-feeds
 * Description: Embeds the NYC In Focus live event map from GitHub Pages using the restored staged-first Field Desk runtime.
 * Version: 1.2.1
 * Author: NYC In Focus
 * License: GPL-2.0-or-later
 * Text Domain: nycif-events-map
 */

if (!defined('ABSPATH')) {
    exit;
}

define('NYCIF_EVENTS_MAP_VERSION', '1.2.1');
define('NYCIF_MAP_EMBED_URL', 'https://setoxxx.github.io/nycif-field-desk/');
define('NYCIF_STAGED_FEED_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json');
define('NYCIF_ALL_FEED_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_all_radar_map_events.json');
define('NYCIF_DASHBOARD_URL', 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-live-pipeline-dashboard.json');

/**
 * Register shortcode [nycif_events_map].
 *
 * Attributes:
 * - height: iframe height CSS value, default 85vh.
 * - cache: Field Desk cache/version token, default map-restore-v02.
 * - reset_filters: set to 1 for the one-time restored-default migration.
 */
function nycif_events_map_shortcode($atts) {
    $atts = shortcode_atts(
        array(
            'height'        => '85vh',
            'cache'         => 'map-restore-v02',
            'reset_filters' => '1',
        ),
        $atts,
        'nycif_events_map'
    );

    $height = sanitize_text_field($atts['height']);
    if (!preg_match('/^\d+(?:\.\d+)?(?:px|vh|vw|rem|em|%)$/', $height)) {
        $height = '85vh';
    }

    $query_args = array(
        'v' => sanitize_text_field($atts['cache']),
    );

    if ('1' === (string) $atts['reset_filters']) {
        $query_args['resetFilters'] = '1';
    }

    $src = add_query_arg($query_args, NYCIF_MAP_EMBED_URL);

    return sprintf(
        '<div class="nycif-events-map-wrap" style="width:100%%;max-width:100%%;margin:0 auto;">'
        . '<iframe class="nycif-events-map-iframe" title="NYC In Focus Event Map" '
        . 'src="%s" style="width:100%%;height:%s;border:0;border-radius:12px;" '
        . 'loading="eager" referrerpolicy="no-referrer-when-downgrade" '
        . 'allow="geolocation; fullscreen" allowfullscreen></iframe>'
        . '<p class="nycif-events-map-caption" style="font-size:12px;color:#666;margin-top:8px;">'
        . 'Live NYC public-event records via the NYCIF staged-first map. Event details may change; confirm before traveling.'
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
    ?>
    <div class="wrap">
        <h1>NYCIF Events Map</h1>
        <p>Plugin version <?php echo esc_html(NYCIF_EVENTS_MAP_VERSION); ?></p>
        <table class="form-table">
            <tr><th>Embed URL</th><td><code><?php echo esc_html(NYCIF_MAP_EMBED_URL); ?></code></td></tr>
            <tr><th>Default runtime URL</th><td><code><?php echo esc_html(add_query_arg(array('v' => 'map-restore-v02', 'resetFilters' => '1'), NYCIF_MAP_EMBED_URL)); ?></code></td></tr>
            <tr><th>Staged feed</th><td><code><?php echo esc_html(NYCIF_STAGED_FEED_URL); ?></code></td></tr>
            <tr><th>Full feed</th><td><code><?php echo esc_html(NYCIF_ALL_FEED_URL); ?></code></td></tr>
            <tr><th>Pipeline dashboard</th><td><a href="<?php echo esc_url(NYCIF_DASHBOARD_URL); ?>" target="_blank" rel="noopener">Open JSON</a></td></tr>
        </table>
        <p>Shortcode: <code>[nycif_events_map]</code></p>
        <p>Optional: <code>[nycif_events_map height="90vh" cache="custom-bust" reset_filters="0"]</code></p>
        <p><strong>Deployment note:</strong> Merge and verify the Field Desk GitHub Pages restoration before installing this plugin package.</p>
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
