<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="1.0.0" xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
    <NamedLayer>
        <Name>world</Name>
        <UserStyle>
            <Title>red</Title>
            <FeatureTypeStyle>
                <Rule>
                    <PolygonSymbolizer>
                        <Geometry>
                            <PropertyName>the_area</PropertyName>
                        </Geometry>
                        <Stroke>
                            <CssParameter name="stroke">#ff0000</CssParameter>
                        </Stroke>
                        <Fill>
                            <CssParameter name="fill">#ffaaaa</CssParameter>
                        </Fill>
                    </PolygonSymbolizer>
                </Rule>
            </FeatureTypeStyle>
        </UserStyle>
    </NamedLayer>
    <NamedLayer>
        <Name>borders</Name>
        <UserStyle>
            <Title>red</Title>
                <FeatureTypeStyle>
                <Rule>
                    <LineSymbolizer>
                        <Geometry>
                            <PropertyName>center-line</PropertyName>
                        </Geometry>
                        <Stroke>
                            <CssParameter name="stroke">#ff0000</CssParameter>
                        </Stroke>
                    </LineSymbolizer>
                </Rule>
            </FeatureTypeStyle>
        </UserStyle>
    </NamedLayer>
</StyledLayerDescriptor>