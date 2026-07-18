(function (blocks, element, blockEditor, components) {
    'use strict';

    if (!blocks || !element || !blockEditor || !components) {
        return;
    }

    var el = element.createElement;
    var useBlockProps = blockEditor.useBlockProps;
    var Placeholder = components.Placeholder;

    blocks.registerBlockType('nycif/events-map', {
        edit: function () {
            var blockProps = useBlockProps ? useBlockProps() : {};

            return el(
                'div',
                blockProps,
                el(
                    Placeholder,
                    {
                        icon: 'location-alt',
                        label: 'NYCIF Events Map'
                    },
                    el(
                        'p',
                        null,
                        'Server-rendered NYC In Focus public map. Use the shortcode attributes in Code editor for custom embed settings.'
                    )
                )
            );
        },
        save: function () {
            return null;
        }
    });
}(
    window.wp && window.wp.blocks,
    window.wp && window.wp.element,
    window.wp && window.wp.blockEditor,
    window.wp && window.wp.components
));
