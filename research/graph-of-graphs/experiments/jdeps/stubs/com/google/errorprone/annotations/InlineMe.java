package com.google.errorprone.annotations;
import java.lang.annotation.*;
@Retention(RetentionPolicy.CLASS)
public @interface InlineMe {
  String replacement();
  String[] imports() default {};
  String[] staticImports() default {};
}
